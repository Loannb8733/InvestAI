import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.market_data.history.models import AssetPriceHistory
from app.domains.portfolio.models import Asset, AssetType, Portfolio
from app.domains.transactions.models import Transaction, TransactionType
from app.services import fifo_replay

_ZERO = Decimal("0")

_HOLDING_IN = (
    TransactionType.BUY,
    TransactionType.AIRDROP,
    TransactionType.STAKING_REWARD,
    TransactionType.TRANSFER_IN,
    TransactionType.CONVERSION_IN,
)
_HOLDING_OUT = (TransactionType.SELL, TransactionType.TRANSFER_OUT, TransactionType.CONVERSION_OUT)
_TAXABLE = (TransactionType.SELL, TransactionType.CONVERSION_OUT)
_LONG_TERM_DAYS = 730

PriceCache = dict[date, dict[str, Decimal]]


@dataclass
class TaxEvent2086:
    """Cession imposable : cession_price = qté * prix - frais, gain_loss = cession_price - acquisition_fraction."""

    date: datetime
    symbol: str
    event_type: str
    quantity: float
    unit_price: float
    cession_price: float
    portfolio_value: float
    total_acquisition_cost: float
    acquisition_fraction: float
    gain_loss: float
    holding_period: str
    fees: float


@dataclass
class TaxSummary2086:
    year: int
    total_cessions: float
    total_acquisitions_fraction: float
    total_plus_values: float
    total_moins_values: float
    net_plus_value: float
    nb_cessions: int
    nb_court_terme: int
    nb_long_terme: int
    flat_tax_30: float
    ir_12_8: float
    ps_17_2: float
    events: list[TaxEvent2086] = field(default_factory=list)


@dataclass(frozen=True)
class TaxMode:
    """Rejeu fiscal : TAX_MODE corrige les quatre divergences accidentelles que TAX_MODE_LEGACY fige pour comparaison.

    Legacy : ordre SQL brut au lieu de TRANSFER_OUT avant TRANSFER_IN simultané, pas de repli external_id pour les
    conversions, frais réseau des transferts non rognés, CONVERSION_OUT non apparié consommé et taxé (pas de sursis).
    """

    config: fifo_replay.ReplayConfig
    canonical_sort: bool


def _tax_mode(converged: bool) -> TaxMode:
    policy = fifo_replay.UnmatchedConversionOutPolicy
    config = fifo_replay.ReplayConfig(
        portfolio_currency="EUR",
        reward_basis=fifo_replay.RewardBasis.ZERO,
        conversion_dest_basis=fifo_replay.ConversionDestBasis.CARRY_COST,
        unmatched_transfer_in=fifo_replay.UnmatchedTransferInPolicy.ZERO,
        fee_handling=fifo_replay.FeeHandling.TX_CURRENCY,
        seed_stablecoin_layers=False,
        skip_null_executed_at=True,
        unmatched_conversion_out=policy.PRESERVE if converged else policy.CONSUME,
        trim_transfer_network_fee=converged,
        conversion_external_id_fallback=converged,
    )
    return TaxMode(config=config, canonical_sort=converged)


TAX_MODE_LEGACY = _tax_mode(converged=False)
TAX_MODE = _tax_mode(converged=True)


def _empty_summary(year: int) -> TaxSummary2086:
    return TaxSummary2086(year, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, [])


@dataclass
class _CessionLedger:
    year_start: datetime
    year_end: datetime
    total_acquisition_cost: Decimal = _ZERO
    events: list[TaxEvent2086] = field(default_factory=list)
    cession_dates: set[date] = field(default_factory=set)

    def on_event(self, ev: fifo_replay.ReplayEvent) -> None:
        if ev.kind == "BUY":
            self.total_acquisition_cost += ev.total_cost
            return
        if ev.kind == "CONVERSION_IN_FEE":
            self.total_acquisition_cost += ev.fee
            return
        if ev.kind not in ("SELL", "CONVERSION_OUT"):
            return
        self.total_acquisition_cost -= ev.cost_removed
        if ev.kind == "CONVERSION_OUT":
            self.total_acquisition_cost += ev.dest_cost
        tx_dt = cast(datetime, ev.tx_dt)
        if self.year_start <= tx_dt <= self.year_end:
            self.cession_dates.add(tx_dt.date())
            self.events.append(self._event(ev, tx_dt))

    def _event(self, ev: fifo_replay.ReplayEvent, tx_dt: datetime) -> TaxEvent2086:
        tx = cast(Transaction, ev.tx)
        cession_price = ev.quantity * ev.price - ev.fee
        long_term = ev.oldest_acquired_at and (tx_dt - ev.oldest_acquired_at).days >= _LONG_TERM_DAYS
        return TaxEvent2086(
            date=cast(datetime, tx.executed_at),
            symbol=ev.symbol,
            event_type=tx.transaction_type.value,
            quantity=float(ev.quantity),
            unit_price=float(ev.price),
            cession_price=float(cession_price),
            portfolio_value=0.0,
            total_acquisition_cost=float(self.total_acquisition_cost),
            acquisition_fraction=0.0,
            gain_loss=0.0,
            holding_period="long_terme" if long_term else "court_terme",
            fees=float(ev.fee),
        )


def _apply_holding(holdings: dict[str, Decimal], ttype: TransactionType, sym: str, qty: Decimal) -> None:
    if ttype in _HOLDING_IN:
        holdings[sym] += qty
    elif ttype in _HOLDING_OUT:
        holdings[sym] = max(_ZERO, holdings[sym] - qty)


def _portfolio_value(
    holdings: dict[str, Decimal], sym: str, tx: Transaction, day_prices: dict[str, Decimal]
) -> Decimal:
    portfolio_value = _ZERO
    for held_sym, held_qty in holdings.items():
        if held_qty > _ZERO:
            if held_sym == sym:
                sell_fx = Decimal(str(tx.conversion_rate)) if tx.conversion_rate else Decimal("1")
                portfolio_value += held_qty * Decimal(str(tx.price or 0)) * sell_fx
            else:
                hist_price = day_prices.get(held_sym.upper(), _ZERO)
                portfolio_value += held_qty * hist_price
    return portfolio_value


def _apply_2086_formula(ev: TaxEvent2086, portfolio_value: Decimal) -> None:
    cession_d = Decimal(str(ev.cession_price))
    total_acq_d = Decimal(str(ev.total_acquisition_cost))
    acq_fraction = float(total_acq_d * cession_d / portfolio_value) if portfolio_value > 0 else 0.0
    ev.portfolio_value = float(portfolio_value)
    ev.acquisition_fraction = acq_fraction
    ev.gain_loss = ev.cession_price - acq_fraction


def _fill_portfolio_values(
    replay_txs: list[Transaction], asset_map: dict[uuid.UUID, Asset], ledger: _CessionLedger, price_cache: PriceCache
) -> None:
    holdings: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    events = ledger.events
    event_idx = 0
    for tx in replay_txs:
        asset = asset_map.get(tx.asset_id)
        if not asset or not tx.executed_at:
            continue
        sym = asset.symbol.upper()
        tx_dt = tx.executed_at
        if tx_dt.tzinfo is None:
            tx_dt = tx_dt.replace(tzinfo=UTC)
        _apply_holding(holdings, tx.transaction_type, sym, Decimal(str(tx.quantity)))
        is_in_year = ledger.year_start <= tx_dt <= ledger.year_end
        is_taxable = tx.transaction_type in _TAXABLE
        if not (is_in_year and is_taxable and event_idx < len(events)):
            continue
        ev = events[event_idx]
        if ev.date == tx.executed_at and ev.symbol == sym:
            _apply_2086_formula(ev, _portfolio_value(holdings, sym, tx, price_cache.get(tx_dt.date(), {})))
            event_idx += 1


def _summarize(year: int, events: list[TaxEvent2086]) -> TaxSummary2086:
    total_cessions = sum(e.cession_price for e in events)
    total_acq_fraction = sum(e.acquisition_fraction for e in events)
    total_pv = sum(e.gain_loss for e in events if e.gain_loss > 0)
    total_mv = sum(e.gain_loss for e in events if e.gain_loss < 0)
    net_pv = total_pv + total_mv
    nb_ct = sum(1 for e in events if e.holding_period == "court_terme")
    nb_lt = sum(1 for e in events if e.holding_period == "long_terme")
    taxable = max(0.0, net_pv)
    ir = taxable * 0.128
    ps = taxable * 0.172
    flat_tax = ir + ps
    return TaxSummary2086(
        year=year,
        total_cessions=total_cessions,
        total_acquisitions_fraction=total_acq_fraction,
        total_plus_values=total_pv,
        total_moins_values=total_mv,
        net_plus_value=net_pv,
        nb_cessions=len(events),
        nb_court_terme=nb_ct,
        nb_long_terme=nb_lt,
        flat_tax_30=flat_tax,
        ir_12_8=ir,
        ps_17_2=ps,
        events=events,
    )


class TaxMixin:
    async def _get_historical_prices(
        self, db: AsyncSession, symbols: list[str], price_date: date
    ) -> dict[str, Decimal]:
        if not symbols:
            return {}
        history = AssetPriceHistory
        result = await db.execute(
            select(history.symbol, history.price_eur).where(
                history.symbol.in_(symbols), history.price_date == price_date
            )
        )
        prices: dict[str, Decimal] = {row[0].upper(): Decimal(str(row[1])) for row in result.all()}
        missing = [s for s in symbols if s.upper() not in prices]
        if missing:
            fallback_start = price_date - timedelta(days=7)
            fb_result = await db.execute(
                select(history.symbol, history.price_eur, history.price_date)
                .where(history.symbol.in_(missing), history.price_date.between(fallback_start, price_date))
                .order_by(history.symbol, history.price_date.desc())
            )
            seen: set[str] = set()
            for row in fb_result.all():
                sym_upper = row[0].upper()
                if sym_upper not in seen:
                    prices[sym_upper] = Decimal(str(row[1]))
                    seen.add(sym_upper)
        return prices

    async def compute_tax_2086(
        self, db: AsyncSession, user_id: str, year: int, *, mode: TaxMode = TAX_MODE
    ) -> TaxSummary2086:
        """Plus-values crypto selon le 2086 (art. 150 VH bis CGI), rejeu FIFO de toutes les années.

        PV = prix de cession - coût total d'acquisition * prix de cession / valeur du portefeuille, où le coût cumule
        achats et coût reporté des conversions (hors transferts) et la valeur du portefeuille vient des cours
        historiques en EUR du jour de cession (repli jusqu'à 7 jours avant). Long terme à partir de 730 jours.
        """
        result = await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))
        portfolio_ids = [p.id for p in result.scalars().all()]
        if not portfolio_ids:
            return _empty_summary(year)
        asset_result = await db.execute(select(Asset).where(Asset.portfolio_id.in_(portfolio_ids)))
        crypto_assets = [a for a in asset_result.scalars().all() if a.asset_type == AssetType.CRYPTO]
        crypto_asset_ids = [a.id for a in crypto_assets]
        if not crypto_asset_ids:
            return _empty_summary(year)
        asset_map = {a.id: a for a in crypto_assets}
        aid_to_symbol: dict[str, str] = {str(a.id): a.symbol.upper() for a in crypto_assets}
        trans_result = await db.execute(
            select(Transaction)
            .where(Transaction.asset_id.in_(crypto_asset_ids))
            .order_by(Transaction.executed_at.asc())
        )
        all_transactions = list(trans_result.scalars().all())
        replay_txs = fifo_replay.sort_transactions(all_transactions) if mode.canonical_sort else all_transactions

        ledger = _CessionLedger(datetime(year, 1, 1, tzinfo=UTC), datetime(year, 12, 31, 23, 59, 59, tzinfo=UTC))
        fifo_replay.replay(replay_txs, aid_to_symbol, mode.config, on_event=ledger.on_event)

        all_symbols_ever = set(aid_to_symbol.values())
        price_cache: PriceCache = {}
        for d in ledger.cession_dates:
            price_cache[d] = await self._get_historical_prices(db, list(all_symbols_ever), d)
        _fill_portfolio_values(replay_txs, asset_map, ledger, price_cache)
        return _summarize(year, ledger.events)
