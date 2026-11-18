"""Simulation passée d'une règle paramétrée sur les clôtures journalières enregistrées.

Seuls les paramètres de l'utilisateur et l'historique de prix (``asset_price_history``) entrent dans le calcul :
ni ses positions, ni sa liquidité, ni les signaux du moteur de prévision. Le résultat décrit ce que la règle
aurait donné, il ne dit rien de ce qu'elle donnera.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.market_data.history.models import AssetPriceHistory
from app.domains.strategies.disclaimer import BACKTEST_NOTE
from app.domains.strategies.performance import _price_at
from app.domains.strategies.schemas import (
    BacktestResult,
    BacktestTrade,
    DcaParams,
    ProfitTakingParams,
    RebalanceParams,
    VcaParams,
)
from app.domains.strategies.templates import TemplateParamsModel, rebalance_trades, schedule_dates

Series = list[tuple[date, float]]
MAX_TRADES = 200
_LOOKBACK_DAYS = 7
_MIN_TRADE_EUR = 0.01


@dataclass
class _Book:
    units: dict[str, float] = field(default_factory=dict)
    invested: float = 0.0
    withdrawn: float = 0.0
    simulated: int = 0
    missing: int = 0
    trades: list[dict[str, Any]] = field(default_factory=list)

    def buy(self, d: date, symbol: str, amount: float, price: float) -> None:
        self.units[symbol] = self.units.get(symbol, 0.0) + amount / price
        self.invested += amount
        self.trades.append({"date": d, "action": "BUY", "symbol": symbol, "amount": round(amount, 2), "price": price})

    def sell(self, d: date, symbol: str, amount: float, price: float) -> None:
        self.units[symbol] = max(self.units.get(symbol, 0.0) - amount / price, 0.0)
        self.withdrawn += amount
        self.trades.append({"date": d, "action": "SELL", "symbol": symbol, "amount": round(amount, 2), "price": price})

    def value(self, prices: dict[str, float]) -> float:
        return sum(units * prices[s] for s, units in self.units.items() if units > 0)


def params_symbols(params: TemplateParamsModel) -> list[str]:
    if isinstance(params, DcaParams):
        return [a.symbol for a in params.assets]
    if isinstance(params, RebalanceParams):
        return [line.symbol for line in params.lines if line.target_pct > 0]
    return [params.symbol]


async def load_closes(db: AsyncSession, symbols: list[str], since: date) -> dict[str, Series]:
    """Clôtures EUR des ``symbols`` depuis ``since`` (moins une semaine de tolérance), triées par date."""
    result = await db.execute(
        select(AssetPriceHistory.symbol, AssetPriceHistory.price_date, AssetPriceHistory.price_eur)
        .where(
            AssetPriceHistory.symbol.in_([s.upper() for s in symbols]),
            AssetPriceHistory.price_date >= since - timedelta(days=_LOOKBACK_DAYS),
        )
        .order_by(AssetPriceHistory.symbol, AssetPriceHistory.price_date)
    )
    closes: dict[str, Series] = {}
    for symbol, price_date, price in result.all():
        closes.setdefault(symbol.upper(), []).append((price_date, float(price)))
    return closes


def _price(closes: dict[str, Series], symbol: str, d: date) -> float | None:
    found = _price_at(closes.get(symbol, []), d)
    return found[0] if found else None


def _unavailable(reason: str) -> BacktestResult:
    return BacktestResult(available=False, reason=reason, note=BACKTEST_NOTE)


def _result(
    book: _Book,
    start: date,
    end: date,
    planned: int,
    final_value: float,
    benchmark: tuple[str, float] | None = None,
) -> BacktestResult:
    pnl = final_value + book.withdrawn - book.invested
    return BacktestResult(
        available=True,
        start_date=start,
        end_date=end,
        events_planned=planned,
        events_simulated=book.simulated,
        missing_prices=book.missing,
        invested_eur=round(book.invested, 2),
        withdrawn_eur=round(book.withdrawn, 2),
        final_value_eur=round(final_value, 2),
        pnl_eur=round(pnl, 2),
        pnl_pct=round(pnl / book.invested * 100, 2) if book.invested > 0 else None,
        benchmark_label=benchmark[0] if benchmark else None,
        benchmark_value_eur=round(benchmark[1], 2) if benchmark else None,
        trades=[BacktestTrade(**trade) for trade in book.trades[:MAX_TRADES]],
        trades_truncated=len(book.trades) > MAX_TRADES,
        note=BACKTEST_NOTE,
    )


def _simulate_dca(params: DcaParams, closes: dict[str, Series], start: date, end: date) -> BacktestResult:
    dates = schedule_dates(start, params.frequency, params.periods)
    book = _Book()
    for d in (d for d in dates if d <= end):
        book.simulated += 1
        for asset in params.assets:
            price = _price(closes, asset.symbol, d)
            if price is None:
                book.missing += 1
                continue
            book.buy(d, asset.symbol, params.amount_per_period * asset.weight_pct / 100, price)
    if book.invested <= 0:
        return _unavailable("Aucun prix enregistré aux dates simulées")
    last = {s: _price(closes, s, end) or 0.0 for s in book.units}
    return _result(book, start, end, len(dates), book.value(last))


def _simulate_vca(params: VcaParams, closes: dict[str, Series], start: date, end: date) -> BacktestResult:
    dates = schedule_dates(start, params.frequency, params.periods)
    book = _Book()
    symbol = params.symbol
    for k, d in enumerate((d for d in dates if d <= end), start=1):
        book.simulated += 1
        price = _price(closes, symbol, d)
        if price is None:
            book.missing += 1
            continue
        gap = params.target_increment * k - book.units.get(symbol, 0.0) * price
        if gap >= _MIN_TRADE_EUR:
            book.buy(d, symbol, min(gap, params.max_per_period or gap), price)
        elif gap <= -_MIN_TRADE_EUR and params.allow_sell:
            book.sell(d, symbol, min(-gap, book.units.get(symbol, 0.0) * price), price)
    if book.invested <= 0:
        return _unavailable("Aucun prix enregistré aux dates simulées")
    return _result(book, start, end, len(dates), book.value({symbol: _price(closes, symbol, end) or 0.0}))


def _simulate_profit_taking(
    params: ProfitTakingParams, closes: dict[str, Series], start: date, end: date
) -> BacktestResult:
    symbol = params.symbol
    start_price = _price(closes, symbol, start)
    if start_price is None:
        return _unavailable(f"Pas de cours enregistré pour {symbol} autour du {start.strftime('%d/%m/%Y')}")
    book = _Book(units={symbol: params.quantity}, invested=params.quantity * start_price)
    remaining = list(params.tiers)
    for d, close in closes[symbol]:
        if d <= start or d > end:
            continue
        while remaining and close >= remaining[0].price:
            tier = remaining.pop(0)
            book.sell(d, symbol, params.quantity * tier.sell_pct / 100 * close, close)
            book.simulated += 1
    last_price = _price(closes, symbol, end) or 0.0
    benchmark = ("Conserver toute la quantité", params.quantity * last_price)
    return _result(book, start, end, len(params.tiers), book.value({symbol: last_price}), benchmark)


def _simulate_rebalance(params: RebalanceParams, closes: dict[str, Series], start: date, end: date) -> BacktestResult:
    """Capital initial (valeurs saisies + apport) placé à l'allocation cible au départ ; les rééquilibrages
    s'autofinancent (ventes = achats), le capital engagé reste donc l'investissement initial."""
    targets = {line.symbol: line.target_pct for line in params.lines if line.target_pct > 0}
    capital = sum(line.current_value for line in params.lines) + params.contribution
    start_prices = {s: _price(closes, s, start) for s in targets}
    missing = [s for s, p in start_prices.items() if p is None]
    if missing:
        return _unavailable(f"Pas de cours enregistré pour {', '.join(missing)} autour du {start.strftime('%d/%m/%Y')}")
    book = _Book()
    for s, weight in targets.items():
        book.buy(start, s, capital * weight / 100, start_prices[s])  # type: ignore[arg-type]
    hold_units = dict(book.units)
    book.simulated = 1
    dates = schedule_dates(start, params.frequency, params.periods)
    for d in (d for d in dates[1:] if d <= end):
        prices = {s: _price(closes, s, d) for s in targets}
        if any(p is None for p in prices.values()):
            book.missing += 1
            continue
        known: dict[str, float] = {s: p for s, p in prices.items() if p is not None}
        book.simulated += 1
        current = {s: book.units.get(s, 0.0) * known[s] for s in targets}
        trades = rebalance_trades(current, targets, 0.0, params.threshold_pct)
        for s, delta in (trades or {}).items():
            if delta >= _MIN_TRADE_EUR:
                book.buy(d, s, delta, known[s])
            elif delta <= -_MIN_TRADE_EUR:
                book.sell(d, s, -delta, known[s])
    last = {s: _price(closes, s, end) or 0.0 for s in targets}
    book.invested, book.withdrawn = capital, 0.0
    hold_value = sum(units * last[s] for s, units in hold_units.items())
    return _result(book, start, end, len(dates), book.value(last), ("Ne jamais rééquilibrer", hold_value))


def simulate_on_history(params: TemplateParamsModel, closes: dict[str, Series], start: date) -> BacktestResult:
    """Rejoue la règle depuis ``start`` jusqu'à la dernière clôture commune aux actifs concernés."""
    symbols = params_symbols(params)
    absent = [s for s in symbols if not closes.get(s)]
    if absent:
        return _unavailable(f"Pas d'historique de prix enregistré pour {', '.join(absent)}")
    end = min(closes[s][-1][0] for s in symbols)
    if start >= end:
        return _unavailable(f"La date de départ doit précéder la dernière clôture enregistrée ({end:%d/%m/%Y})")
    if isinstance(params, DcaParams):
        return _simulate_dca(params, closes, start, end)
    if isinstance(params, VcaParams):
        return _simulate_vca(params, closes, start, end)
    if isinstance(params, ProfitTakingParams):
        return _simulate_profit_taking(params, closes, start, end)
    return _simulate_rebalance(params, closes, start, end)


async def run_backtest(db: AsyncSession, params: TemplateParamsModel, start: date) -> BacktestResult:
    closes = await load_closes(db, params_symbols(params), start)
    return simulate_on_history(params, closes, start)
