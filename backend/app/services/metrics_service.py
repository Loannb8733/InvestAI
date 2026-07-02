"""Metrics calculation service for portfolio analysis."""

import asyncio
import logging
import math
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.historical_data import HistoricalDataFetcher
from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction
from app.services.fifo import consume_fifo, extract_fifo_layers
from app.services.price_service import price_service

logger = logging.getLogger(__name__)

# In-memory cache for dashboard metrics: {(user_id, days): (timestamp, result)}
_dashboard_cache: Dict[Tuple[str, int], Tuple[float, Dict]] = {}
_DASHBOARD_CACHE_TTL = 120  # 2 minutes
_MAX_DASHBOARD_CACHE = 200  # max entries before eviction

# Single-flight guard: the in-flight recompute future per cache key. When several
# requests miss the cache at once (typically right after the TTL expires), only
# the first recomputes; the rest await that same future instead of stampeding the
# DB/CPU with N identical full-FIFO recomputes.
_dashboard_inflight: Dict[Tuple, "asyncio.Future"] = {}


def _cache_put_dashboard(key: Tuple, value: Tuple) -> None:
    """Insert into bounded dashboard cache, evicting oldest entries if full."""
    if len(_dashboard_cache) >= _MAX_DASHBOARD_CACHE:
        evict_count = max(1, _MAX_DASHBOARD_CACHE // 4)
        sorted_keys = sorted(_dashboard_cache, key=lambda k: _dashboard_cache[k][0])
        for k in sorted_keys[:evict_count]:
            del _dashboard_cache[k]
    _dashboard_cache[key] = value


def invalidate_dashboard_cache(user_id: str) -> None:
    """Evict all cached dashboard entries for a given user.

    Call after any mutation (create/update/delete transaction) so the next
    dashboard or report request picks up fresh data immediately.
    """
    keys_to_delete = [k for k in _dashboard_cache if k[0] == user_id]
    for k in keys_to_delete:
        del _dashboard_cache[k]


# Fiat currencies -> counted as cash
FIAT_SYMBOLS = {"EUR", "USD", "GBP", "CHF", "CAD", "AUD", "JPY"}

# Stablecoins -> separate card, excluded from investment metrics
STABLECOIN_SYMBOLS = {
    "USDT",
    "USDC",
    "BUSD",
    "DAI",
    "TUSD",
    "USDP",
    "GUSD",
    "FRAX",
    "LUSD",
    "USDG",
    "PYUSD",
    "FDUSD",
    "EURC",
    "EURT",
}


def is_fiat(symbol: str) -> bool:
    return symbol.upper() in FIAT_SYMBOLS


def is_stablecoin(symbol: str) -> bool:
    return symbol.upper() in STABLECOIN_SYMBOLS


def is_cash_like(symbol: str) -> bool:
    return is_fiat(symbol) or is_stablecoin(symbol)


# Canonical alias — use this across the codebase
is_liquidity = is_cash_like


# Gold / safe-haven asset detection
_GOLD_SYMBOLS = {"PAXG", "XAUT", "GLD", "IAU", "SGOL", "GOLD"}


def is_safe_haven(symbol: str) -> bool:
    """Return True for gold-backed tokens and ETFs."""
    return symbol.upper() in _GOLD_SYMBOLS


def _conversion_dest_unit_cost(
    cost_removed: Decimal,
    matched_qty: Decimal,
    recorded_price: Decimal,
) -> Decimal:
    """Cost basis per unit for a conversion destination.

    A crypto-to-crypto conversion is a disposal of the source plus a re-acquisition
    of the destination: the destination's cost basis is its market value on the
    conversion day, i.e. the **recorded CONVERSION_IN price**. We use that whenever
    it is known.

    The legacy model instead *carried* the source's consumed cost
    (``cost_removed / matched_qty``). A mis-matched or chained conversion can pair a
    large source cost with a tiny destination qty, concentrating cost into
    impossible per-unit values (observed up to ~500k EUR/BTC in prod) that overstate
    the cost basis and compound across conversion chains. We keep the carry only as
    a fallback for the rare case where the destination price was not recorded.
    """
    _Z = Decimal("0")
    if matched_qty <= _Z:
        return _Z
    if recorded_price > _Z:
        return recorded_price
    return cost_removed / matched_qty


def _ci_price_in_portfolio_ccy(price, conversion_rate) -> Decimal:
    """Recorded CONVERSION_IN price expressed in the portfolio currency.

    ``price`` is stored in the leg's own trade currency (e.g. a USD-quoted swap);
    ``conversion_rate`` is portfolio units per 1 unit of that currency (``None``
    means the price is already in the portfolio currency). Every other leg applies
    this same rate, so the conversion destination's cost basis must too — otherwise
    a USD-quoted CONVERSION_IN is carried as if it were EUR.
    """
    p = Decimal(str(price or 0))
    fx = Decimal(str(conversion_rate)) if conversion_rate else Decimal("1")
    return p * fx


def compute_cump_pru(
    all_txs: list,
    aid_to_symbol: Dict[str, str],
    aid_to_exchange: Dict[str, str],
) -> Dict[Tuple[str, str], Decimal]:
    """Compute CUMP (Weighted Average Cost) PRU per (symbol, exchange).

    Rules:
    1. PRU = (Σ buy_amount + fees) / Σ buy_qty  — fee-inclusive weighted average
    2. Sells reduce qty but never change PRU
    3. Position reset: when qty falls to 0, the next buy starts a fresh average
    """
    from app.models.transaction import TransactionType as TxType

    _ZERO = Decimal("0")
    state: Dict[Tuple[str, str], Dict] = {}

    for tx in all_txs:
        aid = str(tx.asset_id)
        sym = aid_to_symbol.get(aid, "")
        if not sym:
            continue
        exch = aid_to_exchange.get(aid, "")
        fkey = (sym, exch)

        if fkey not in state:
            state[fkey] = {
                "cost": _ZERO,
                "buy_qty": _ZERO,
                "current_qty": _ZERO,
                "pru": _ZERO,
                "needs_reset": False,
            }

        s = state[fkey]
        qty = Decimal(str(tx.quantity or 0))
        # Cost basis is tracked in the PORTFOLIO currency. The trade price/fee are
        # in ``tx.currency``, so convert them via the FX rate captured at execution
        # (``conversion_rate`` = portfolio units per 1 unit of tx currency; defaults
        # to 1 for same-currency trades). Without this, a USD/USDT-pair buy stored
        # the raw USD price as the PRU — ~8-9% above the EUR cost basis the FIFO
        # engine reports (which already applies this same rate), leaving the
        # displayed PRU inconsistent with the gain/loss. (FIN-01 parity.)
        fx = Decimal(str(tx.conversion_rate)) if getattr(tx, "conversion_rate", None) else Decimal("1")
        price = Decimal(str(tx.price or 0)) * fx
        fee = Decimal(str(tx.fee or 0)) * fx
        ttype = tx.transaction_type

        if ttype == TxType.BUY:
            if s["needs_reset"]:
                s["cost"] = _ZERO
                s["buy_qty"] = _ZERO
                s["needs_reset"] = False
            invested = qty * price + fee
            s["cost"] += invested
            s["buy_qty"] += qty
            s["current_qty"] += qty
            if s["buy_qty"] > _ZERO:
                s["pru"] = s["cost"] / s["buy_qty"]

        elif ttype == TxType.SELL:
            s["current_qty"] = max(_ZERO, s["current_qty"] - qty)
            if s["current_qty"] <= _ZERO:
                s["current_qty"] = _ZERO
                s["needs_reset"] = True

        elif ttype == TxType.TRANSFER_IN:
            if price > _ZERO:
                s["cost"] += qty * price + fee
                s["buy_qty"] += qty
            elif s["pru"] > _ZERO:
                # F-06: a zero-price transfer-in of an already-held coin is an
                # internal wallet move; it inherits the running average cost so the
                # PRU stays stable instead of being diluted toward zero. (Unifies
                # behaviour with the FIFO engine's unmatched-transfer handling.)
                s["cost"] += qty * s["pru"]
                s["buy_qty"] += qty
            if s["buy_qty"] > _ZERO:
                s["pru"] = s["cost"] / s["buy_qty"]
            s["current_qty"] += qty

        elif ttype == TxType.TRANSFER_OUT:
            s["current_qty"] = max(_ZERO, s["current_qty"] - qty)

        elif ttype in (TxType.STAKING_REWARD, TxType.AIRDROP):
            s["current_qty"] += qty

        elif ttype == TxType.CONVERSION_IN:
            if price > _ZERO:
                s["cost"] += qty * price
                s["buy_qty"] += qty
                if s["buy_qty"] > _ZERO:
                    s["pru"] = s["cost"] / s["buy_qty"]
            s["current_qty"] += qty

        elif ttype == TxType.CONVERSION_OUT:
            s["current_qty"] = max(_ZERO, s["current_qty"] - qty)

    return {fkey: s["pru"] for fkey, s in state.items() if s["pru"] > _ZERO and not s["needs_reset"]}


class MetricsService:
    """Service for calculating portfolio metrics."""

    async def get_asset_metrics(
        self,
        asset: Asset,
        current_price: Optional[Decimal] = None,
        actual_invested: Optional[Decimal] = None,
        buy_pra: Optional[Decimal] = None,
        cump_pru: Optional[Decimal] = None,
    ) -> Dict:
        """Calculate metrics for a single asset.

        Args:
            actual_invested: Exact FIFO cost basis for this (symbol, exchange).
                             Takes priority over buy_pra for G/L accuracy.
            buy_pra: Symbol-wide undiluted PRA (across all exchanges). Used as
                     fallback when actual_invested is unavailable.
            cump_pru: Live-computed fee-inclusive CUMP PRU from transaction history.
                      Overrides avg_buy_price for display when provided.
        """
        quantity = Decimal(str(asset.quantity))
        avg_buy_price = Decimal(str(asset.avg_buy_price))

        # Coerce cost-basis inputs to Decimal (consistent with current_price below).
        # Production callers pass Decimal, but be robust to float to avoid
        # Decimal/float TypeError when these participate in arithmetic.
        if actual_invested is not None:
            actual_invested = Decimal(str(actual_invested))
        if buy_pra is not None:
            buy_pra = Decimal(str(buy_pra))
        if cump_pru is not None:
            cump_pru = Decimal(str(cump_pru))

        # Display PRU: prefer live-computed CUMP (fee-inclusive) over DB value.
        # Falls back to buy_pra (symbol-wide), then DB avg_buy_price.
        if cump_pru is not None and cump_pru > Decimal("0"):
            avg_buy_price = cump_pru
        elif actual_invested is None and buy_pra is not None and buy_pra > 0:
            avg_buy_price = buy_pra

        # G/L cost basis: FIFO actual_invested > PRA-derived fallback
        if actual_invested is not None:
            total_invested = actual_invested
        else:
            total_invested = quantity * avg_buy_price

        # Current value
        if current_price is None:
            current_value = total_invested
            gain_loss = Decimal("0")
            gain_loss_percent = 0.0
        else:
            current_price = Decimal(str(current_price))
            current_value = quantity * current_price
            gain_loss = current_value - total_invested
            gain_loss_percent = float(gain_loss / total_invested * 100) if total_invested > 0 else 0.0

        return {
            "quantity": float(quantity),
            "avg_buy_price": float(avg_buy_price),
            "total_invested": float(total_invested),
            "current_price": float(current_price) if current_price else None,
            "current_value": float(current_value),
            "gain_loss": float(gain_loss),
            "gain_loss_percent": gain_loss_percent,
        }

    async def _compute_risk_weights(
        self,
        db: AsyncSession,
        symbols: List[str],
        symbol_values: Dict[str, float],
        total_value: float,
        days: int = 90,
    ) -> Dict[str, float]:
        """Compute risk weight per symbol based on historical volatility contribution."""
        if not symbols or total_value <= 0:
            return {}

        from app.models.asset_price_history import AssetPriceHistory

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date()

        result = await db.execute(
            select(
                AssetPriceHistory.symbol,
                AssetPriceHistory.price_date,
                AssetPriceHistory.price_eur,
            )
            .where(
                AssetPriceHistory.symbol.in_([s.upper() for s in symbols]),
                AssetPriceHistory.price_date >= cutoff,
            )
            .order_by(AssetPriceHistory.symbol, AssetPriceHistory.price_date)
        )
        rows = result.all()

        # Group prices by symbol
        symbol_prices: Dict[str, List[float]] = defaultdict(list)
        for row in rows:
            symbol_prices[row[0]].append(float(row[2]))

        # Compute annualized volatility per symbol
        volatilities: Dict[str, float] = {}
        for symbol, prices in symbol_prices.items():
            if len(prices) < 10:
                volatilities[symbol] = 0.0
                continue
            daily_returns = [
                (prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices)) if prices[i - 1] > 0
            ]
            if not daily_returns:
                volatilities[symbol] = 0.0
                continue
            mean_ret = sum(daily_returns) / len(daily_returns)
            variance = sum((r - mean_ret) ** 2 for r in daily_returns) / len(daily_returns)
            volatilities[symbol] = math.sqrt(variance) * math.sqrt(252)

        # Weighted risk contributions
        total_weighted = 0.0
        weighted_vols: Dict[str, float] = {}
        for symbol in symbols:
            s = symbol.upper()
            weight = symbol_values.get(s, 0) / total_value if total_value > 0 else 0
            wv = weight * volatilities.get(s, 0)
            weighted_vols[s] = wv
            total_weighted += wv

        # Normalize to percentages
        risk_weights: Dict[str, float] = {}
        for symbol, wv in weighted_vols.items():
            risk_weights[symbol] = round((wv / total_weighted * 100) if total_weighted > 0 else 0, 2)

        return risk_weights

    async def get_portfolio_metrics(
        self,
        db: AsyncSession,
        portfolio_id: str,
        currency: str = "EUR",
        include_zero_quantity: bool = False,
        min_value_eur: float = 0.10,  # Filter out dust positions worth less than this
    ) -> Dict:
        """Calculate metrics for an entire portfolio."""
        # Get all assets in portfolio
        query = select(Asset).where(
            Asset.portfolio_id == portfolio_id,
        )
        if not include_zero_quantity:
            query = query.where(Asset.quantity > 0)

        result = await db.execute(query)
        all_assets = result.scalars().all()

        # Pre-filter: remove assets with zero quantity (actual dust filtering
        # happens later after live prices are fetched, so we keep all qty > 0 here)
        assets = []
        min_value_threshold = Decimal(str(min_value_eur))
        for asset in all_assets:
            if not include_zero_quantity:
                qty = Decimal(str(asset.quantity))
                avg_price = Decimal(str(asset.avg_buy_price)) if asset.avg_buy_price else Decimal("0")
                current_price = Decimal(str(asset.current_price)) if asset.current_price else Decimal("0")
                best_price = avg_price or current_price
                if best_price > 0:
                    est_value = qty * best_price
                    if est_value < min_value_threshold:
                        continue
                # No price info yet — keep the asset; real value will be
                # determined after live prices are fetched below.
            assets.append(asset)

        if not assets:
            return {
                "total_value": 0.0,
                "total_invested": 0.0,
                "total_gain_loss": 0.0,
                "total_gain_loss_percent": 0.0,
                "assets_count": 0,
                "assets": [],
                "cash_from_stablecoins": 0.0,
                "stablecoins": [],
                "cash_from_fiat": 0.0,
                "fiat_assets": [],
            }

        # Separate into: investments, stablecoins, fiat cash
        # Exclude CROWDFUNDING — managed via dedicated /crowdfunding endpoints
        investment_assets = [a for a in assets if not is_cash_like(a.symbol) and a.asset_type != AssetType.CROWDFUNDING]
        stablecoin_assets = [a for a in assets if is_stablecoin(a.symbol)]
        fiat_assets = [a for a in assets if is_fiat(a.symbol)]

        # Batch-fetch total fees, actual invested, and first buy date per asset
        inv_asset_ids = [a.id for a in investment_assets]
        fees_map: Dict[str, float] = {}
        invested_map: Dict[str, Decimal] = {}  # actual cost basis per asset (BUY+CONV_IN+TRANSFER_IN)
        buy_pra_by_sym: Dict[str, Decimal] = {}  # undiluted PRA per symbol
        sym_to_aids: Dict[str, list] = {}  # symbol -> list of Asset objects
        cost_by_sym: Dict[str, Decimal] = {}  # symbol -> total cost basis
        cost_qty_by_sym: Dict[str, Decimal] = {}  # symbol -> cost-bearing qty
        buy_cost_by_sym: Dict[str, Decimal] = {}  # symbol -> total buy cost
        first_buy_map: Dict[str, datetime] = {}  # first transaction date per asset
        # Fees/dividends needing currency conversion: entries are either
        #   (fkey: Tuple[str,str], amount: Decimal, ccy: str)  for fees
        #   (str starting "__div__", amount: Decimal, ccy: str) for dividends
        _pending_fee_conversions: list = []

        # Forex setup — must be available before FIFO so fees can be converted
        # immediately after the FIFO pass, before per-asset G/L is computed.
        from app.core.redis_client import cache_forex_rate, get_cached_forex_rate
        from app.services.fx_history_service import FxHistoryService

        target = currency.upper()
        usd_to_target = 1.0
        eur_to_target = 1.0
        # Last-resort constants, used ONLY when live, cached, AND the persisted ECB
        # table all fail. They are always flagged stale so the UI never presents a
        # guessed rate as a real quote.
        _HARDCODED_FALLBACK_RATES = {
            "EUR": {"USD": 1.09, "CHF": 0.94, "GBP": 0.86},
            "USD": {"EUR": 0.92, "CHF": 0.86, "GBP": 0.79},
        }
        forex_stale = False
        _fx_hist = FxHistoryService(db)

        async def _fx_last_known(from_ccy: str, to_ccy: str) -> Optional[float]:
            """Last-known real rate from the persisted ECB daily table (forward-filled).

            Tries the direct pair, then the inverse, so we fall back to a *real*
            reference rate (e.g. last business day's ECB fix) instead of a guess
            whenever any history exists. Network-free (DB read only).
            """
            try:
                direct = await _fx_hist.get_rate(date.today(), from_ccy, to_ccy)
                if direct:
                    return float(direct)
                inverse = await _fx_hist.get_rate(date.today(), to_ccy, from_ccy)
                if inverse and float(inverse) != 0:
                    return 1.0 / float(inverse)
            except Exception as e:  # noqa: BLE001 - DB fallback is best-effort
                logger.warning("FX history fallback failed for %s->%s: %s", from_ccy, to_ccy, e)
            return None

        async def _get_rate_with_cache(from_ccy: str, to_ccy: str) -> Tuple[float, bool]:
            """Resolve an FX rate as (rate, stale).

            Order: live API → Redis cache → persisted ECB last-known → constant.
            ``stale`` is False only for a live or freshly-cached quote; any fallback
            to the persisted table or the last-resort constant is flagged stale so
            the API/UI can warn the conversion may not reflect the current market.
            """
            try:
                rate = await price_service.get_forex_rate(from_ccy, to_ccy)
                if rate:
                    rate_f = float(rate)
                    await cache_forex_rate(from_ccy, to_ccy, rate_f)
                    return rate_f, False
            except Exception as e:  # noqa: BLE001 - degrade gracefully, never raise
                logger.warning("Live forex fetch failed for %s->%s: %s", from_ccy, to_ccy, e)
            cached = await get_cached_forex_rate(from_ccy, to_ccy)
            if cached and cached.get("rate"):
                return cached["rate"], False
            last_known = await _fx_last_known(from_ccy, to_ccy)
            if last_known is not None:
                return last_known, True
            fallback = _HARDCODED_FALLBACK_RATES.get(from_ccy, {}).get(to_ccy, 1.0)
            logger.warning(
                "No live/cached/persisted FX for %s->%s; using last-resort constant %s",
                from_ccy,
                to_ccy,
                fallback,
            )
            return fallback, True

        if target != "USD":
            usd_to_target, stale = await _get_rate_with_cache("USD", target)
            forex_stale = forex_stale or stale
        if target != "EUR":
            eur_to_target, stale = await _get_rate_with_cache("EUR", target)
            forex_stale = forex_stale or stale

        if inv_asset_ids:
            # Fetch first transaction date per asset (for holding duration)
            first_tx_result = await db.execute(
                select(
                    Transaction.asset_id,
                    func.min(Transaction.executed_at).label("first_date"),
                )
                .where(Transaction.asset_id.in_(inv_asset_ids))
                .group_by(Transaction.asset_id)
            )
            first_buy_map = {str(r[0]): r[1] for r in first_tx_result.all() if r[1]}
        if inv_asset_ids:
            from app.models.transaction import TransactionType as TxType

            fee_result = await db.execute(
                select(
                    Transaction.asset_id,
                    func.sum(
                        case(
                            (
                                Transaction.transaction_type == TxType.FEE,
                                Transaction.quantity * Transaction.price,
                            ),
                            else_=func.coalesce(Transaction.fee, 0),
                        )
                    ).label("total_fees"),
                )
                .where(Transaction.asset_id.in_(inv_asset_ids))
                .group_by(Transaction.asset_id)
            )
            fees_map = {str(r[0]): float(r[1] or 0) for r in fee_result.all()}

            # ====== M1: FIFO cost basis per (symbol, exchange) ======
            #
            # Each BUY creates a cost "layer" tied to its exchange.
            # SELLs consume layers FIFO from the SAME exchange.
            # TRANSFER_OUT/IN moves oldest layers to the destination exchange.
            # CONVERSION_OUT/IN consumes source layers FIFO, creates a new
            # layer on the destination (symbol, exchange) with propagated cost.
            #
            # Output: invested_map[asset_id] = total cost basis for that
            #         (symbol, exchange) combination.

            # Fetch ALL transactions for the portfolio (not just inv_asset_ids)
            # to capture conversion sources that may have qty=0 now
            portfolio_id_val = investment_assets[0].portfolio_id
            all_tx_result = await db.execute(
                select(Transaction)
                .join(Asset, Transaction.asset_id == Asset.id)
                .where(Asset.portfolio_id == portfolio_id_val)
                .order_by(Transaction.executed_at, Transaction.id)
            )
            all_txs = all_tx_result.scalars().all()
            # TRANSFER_OUT must be processed before TRANSFER_IN at the same timestamp
            # so FIFO transit layers exist when the matching TRANSFER_IN is consumed.
            _epoch = datetime.min.replace(tzinfo=timezone.utc)
            all_txs = sorted(
                all_txs,
                key=lambda tx: (
                    tx.executed_at or _epoch,
                    0 if tx.transaction_type == TxType.TRANSFER_OUT else 1,
                    str(tx.id),
                ),
            )

            # Fetch ALL portfolio assets (including qty=0) for FIFO symbol/exchange
            # lookups — zero-qty assets may have TRANSFER_OUT transactions whose
            # layers we need to track through to matching TRANSFER_IN.
            all_assets_full_result = await db.execute(select(Asset).where(Asset.portfolio_id == portfolio_id_val))
            all_assets_full = all_assets_full_result.scalars().all()

            # Build symbol + exchange lookups for each asset_id
            aid_to_symbol: Dict[str, str] = {}
            aid_to_exchange: Dict[str, str] = {}
            # F-06: stored average buy price per asset and (symbol-wide), used as the
            # cost-basis proxy for unmatched/zero-price TRANSFER_IN rows so they don't
            # land at zero cost and inflate latent P&L.
            aid_to_avg_price: Dict[str, Decimal] = {}
            sym_avg_price: Dict[str, Decimal] = {}
            for a in all_assets_full:
                aid_to_symbol[str(a.id)] = a.symbol.upper()
                aid_to_exchange[str(a.id)] = (a.exchange or "").strip()
                _avg = Decimal(str(a.avg_buy_price)) if a.avg_buy_price else Decimal("0")
                aid_to_avg_price[str(a.id)] = _avg
                _sym = a.symbol.upper()
                if _avg > 0 and sym_avg_price.get(_sym, Decimal("0")) <= 0:
                    sym_avg_price[_sym] = _avg

            # Compute CUMP PRU from transaction history (fee-inclusive, follows 3 rules)
            cump_pru_by_fkey: Dict[Tuple[str, str], Decimal] = compute_cump_pru(all_txs, aid_to_symbol, aid_to_exchange)

            import re as _re
            from collections import defaultdict as _defaultdict

            _ZERO = Decimal("0")

            # FIFO layers: keyed by (symbol, exchange)
            # Each layer: {
            #   "qty": Decimal,
            #   "unit_cost": Decimal,        # cost in portfolio currency
            #   "unit_cost_base": Decimal,    # cost in transaction currency
            #   "currency": str,              # transaction currency (e.g. "USD")
            #   "fx_rate": Decimal,           # FX rate at purchase (base→portfolio)
            #   "is_paid": bool,
            # }
            # is_paid=True for BUY layers, False for free (airdrop/reward)
            FifoKey = Tuple[str, str]  # (symbol, exchange)
            fifo: Dict[FifoKey, list] = _defaultdict(list)

            # Dividend income tracking per (symbol, exchange)
            dividend_income: Dict[FifoKey, Decimal] = _defaultdict(lambda: _ZERO)

            # Pre-build conversion matching indices
            conv_ins = [tx for tx in all_txs if tx.transaction_type == TxType.CONVERSION_IN]

            def _match_conversion_in(co_tx: Transaction, src_sym: str) -> Tuple[Optional[str], Optional[str], Decimal]:
                """Find the matching CONVERSION_IN for a CONVERSION_OUT.

                Returns (dest_symbol, dest_exchange, matched_qty).
                """
                notes = co_tx.notes or ""
                exch = co_tx.exchange or ""
                co_qty = Decimal(str(co_tx.quantity))

                dest_sym: Optional[str] = None
                dest_exch: Optional[str] = None
                matched_qty = co_qty  # fallback
                matched_price = _ZERO  # recorded dest price on the matched CONVERSION_IN

                if "Crypto.com" in exch or "crypto.com" in exch.lower():
                    for ci in conv_ins:
                        if (ci.notes or "") == notes and (ci.exchange or "") == exch:
                            dest_sym = aid_to_symbol.get(str(ci.asset_id), "")
                            dest_exch = (ci.exchange or "").strip()
                            matched_qty = Decimal(str(ci.quantity))
                            matched_price = _ci_price_in_portfolio_ccy(ci.price, getattr(ci, "conversion_rate", None))
                            break
                else:
                    # Kraken / generic: match trade_id suffix in notes
                    m = _re.search(r"trade_id:convert_sell_(\S+)", notes)
                    if m:
                        suffix = m.group(1)
                        for ci in conv_ins:
                            if f"convert_buy_{suffix}" in (ci.notes or ""):
                                candidate = aid_to_symbol.get(str(ci.asset_id), "")
                                # M3: Verify dest symbol differs from source
                                if candidate and candidate != src_sym:
                                    dest_sym = candidate
                                    dest_exch = (ci.exchange or "").strip()
                                    matched_qty = Decimal(str(ci.quantity))
                                    matched_price = _ci_price_in_portfolio_ccy(
                                        ci.price, getattr(ci, "conversion_rate", None)
                                    )
                                else:
                                    logger.warning(
                                        "Kraken conversion match rejected: " "src=%s == dest=%s (suffix=%s, tx_id=%s)",
                                        src_sym,
                                        candidate,
                                        suffix,
                                        co_tx.id,
                                    )
                                break

                    if not dest_sym:
                        # Fallback: match via external_id for records synced before
                        # the notes-format fix (those records have no trade_id in notes
                        # but do carry external_id="convert_sell_{refid}").
                        ext_id = getattr(co_tx, "external_id", None) or ""
                        if ext_id.startswith("convert_sell_"):
                            suffix = ext_id[len("convert_sell_") :]
                            for ci in conv_ins:
                                ci_ext = getattr(ci, "external_id", None) or ""
                                if ci_ext == f"convert_buy_{suffix}":
                                    candidate = aid_to_symbol.get(str(ci.asset_id), "")
                                    if candidate and candidate != src_sym:
                                        dest_sym = candidate
                                        dest_exch = (ci.exchange or "").strip()
                                        matched_qty = Decimal(str(ci.quantity))
                                        matched_price = _ci_price_in_portfolio_ccy(
                                            ci.price, getattr(ci, "conversion_rate", None)
                                        )
                                    else:
                                        logger.warning(
                                            "Kraken conversion match (ext_id fallback) rejected: "
                                            "src=%s == dest=%s (suffix=%s, tx_id=%s)",
                                            src_sym,
                                            candidate,
                                            suffix,
                                            co_tx.id,
                                        )
                                    break

                return dest_sym, dest_exch, matched_qty, matched_price

            def _consume_fifo(key: FifoKey, qty_to_remove: Decimal) -> Decimal:
                """Remove qty from FIFO layers, return total cost removed."""
                return consume_fifo(fifo.get(key, []), qty_to_remove)

            def _consume_fifo_layers(key: FifoKey, qty_to_remove: Decimal) -> list:
                """Remove qty from FIFO layers, return list of extracted layers
                (preserving original unit costs for transfer/conversion)."""
                return extract_fifo_layers(fifo.get(key, []), qty_to_remove)

            # ---- Single-pass chronological processing ----
            for tx in all_txs:
                sym = aid_to_symbol.get(str(tx.asset_id), "")
                exch = (tx.exchange or "").strip()
                key: FifoKey = (sym, exch)
                qty = Decimal(str(tx.quantity))
                ttype = tx.transaction_type

                if ttype == TxType.BUY:
                    # FX: cost basis is tracked in the PORTFOLIO currency. The trade
                    # price is in the transaction currency, so convert it via the FX
                    # rate captured at execution (conversion_rate = portfolio units per
                    # 1 unit of tx currency; defaults to 1 for same-currency trades).
                    tx_ccy = (tx.currency or "EUR").upper()
                    tx_fx = Decimal(str(tx.conversion_rate)) if tx.conversion_rate else Decimal("1")
                    unit_cost_base = Decimal(str(tx.price or 0))  # price in tx currency
                    total_cost = qty * unit_cost_base * tx_fx  # -> portfolio currency
                    # B1/M2: Include transaction fees in cost basis
                    fee = Decimal(str(tx.fee or 0))
                    if fee > 0:
                        fee_ccy = (tx.fee_currency or tx.currency or "EUR").upper()
                        portfolio_ccy = currency.upper()
                        if fee_ccy == portfolio_ccy:
                            total_cost += fee
                        else:
                            _pending_fee_conversions.append((key, fee, fee_ccy))
                    layer_unit = total_cost / qty if qty > 0 else _ZERO

                    fifo[key].append(
                        {
                            "qty": qty,
                            "unit_cost": layer_unit,
                            "unit_cost_base": unit_cost_base,
                            "currency": tx_ccy,
                            "fx_rate": tx_fx,
                            "is_paid": True,
                        }
                    )

                elif ttype == TxType.SELL:
                    # O5: Warn if sell qty exceeds pool
                    pool_qty = sum(ly["qty"] for ly in fifo.get(key, []))
                    if qty > pool_qty:
                        logger.warning(
                            "Oversell: SELL qty=%s > pool=%s for %s@%s (tx_id=%s)",
                            qty,
                            pool_qty,
                            sym,
                            exch,
                            tx.id,
                        )
                    _consume_fifo(key, qty)

                elif ttype in (TxType.AIRDROP, TxType.STAKING_REWARD):
                    # Rewards/airdrops: use market price at receipt when available
                    # (required for correct fiscal cost basis — staking rewards are
                    # taxable income at their market value on the day received).
                    # Falls back to zero-cost only when no price is recorded.
                    tx_ccy = (tx.currency or "EUR").upper()
                    reward_price = Decimal(str(tx.price or 0))  # price in tx currency
                    tx_fx = Decimal(str(tx.conversion_rate)) if tx.conversion_rate else Decimal("1")
                    # unit_cost must be in the PORTFOLIO currency (EUR): apply fx.
                    fifo[key].append(
                        {
                            "qty": qty,
                            "unit_cost": reward_price * tx_fx,
                            "unit_cost_base": reward_price,
                            "currency": tx_ccy,
                            "fx_rate": tx_fx,
                            "is_paid": reward_price > _ZERO,
                        }
                    )

                elif ttype == TxType.TRANSFER_OUT:
                    # Move oldest layers to a "transit" — the matching TRANSFER_IN
                    # will pick them up. We use the transaction's exchange as source.
                    extracted = _consume_fifo_layers(key, qty)
                    # Store extracted layers temporarily keyed by (sym, "__transit__", tx.id)
                    transit_key = (sym, f"__transit__{tx.id}")
                    fifo[transit_key] = extracted

                elif ttype == TxType.TRANSFER_IN:
                    # Try to find matching TRANSFER_OUT layers in transit
                    # Match by: same symbol, qty ~= transit qty, closest in time
                    matched_transit = None
                    best_match_diff = None
                    for tkey, tlayers in list(fifo.items()):
                        if tkey[0] == sym and tkey[1].startswith("__transit__"):
                            transit_qty = sum(ly["qty"] for ly in tlayers)
                            diff = abs(transit_qty - qty)
                            if best_match_diff is None or diff < best_match_diff:
                                best_match_diff = diff
                                matched_transit = tkey
                    if matched_transit and fifo[matched_transit]:
                        transit_layers = fifo.pop(matched_transit)
                        transit_total_qty = sum(ly["qty"] for ly in transit_layers)
                        if transit_total_qty > qty:
                            # Network fee: transit sent more than received — trim to received qty.
                            # The excess (fee burned on-chain) is discarded from cost basis.
                            temp_key = (sym, f"__trim__{matched_transit[1]}")
                            fifo[temp_key] = transit_layers
                            trimmed = _consume_fifo_layers(temp_key, qty)
                            fifo.pop(temp_key, None)
                            for layer in trimmed:
                                fifo[key].append(layer)
                        else:
                            for layer in transit_layers:
                                fifo[key].append(layer)
                    else:
                        # No matching transit — unmatched/external transfer in.
                        # F-06: do NOT default to zero cost (that treats the whole
                        # position as pure gain and inflates latent P&L). Recover a
                        # cost basis in priority order:
                        #   1. the row's own recorded price (converted to EUR),
                        #   2. this asset's stored avg_buy_price,
                        #   3. the symbol-wide avg_buy_price (same coin elsewhere).
                        # Only when none is known do we fall back to zero cost.
                        tx_ccy = (tx.currency or "EUR").upper()
                        tx_price = Decimal(str(tx.price or 0))
                        if tx_price > _ZERO:
                            tx_fx = Decimal(str(tx.conversion_rate)) if tx.conversion_rate else Decimal("1")
                            unit_cost = tx_price * tx_fx
                            unit_base = tx_price
                            cost_known = True
                        else:
                            # avg_buy_price is already in the portfolio currency (EUR).
                            proxy = aid_to_avg_price.get(str(tx.asset_id), _ZERO)
                            if proxy <= _ZERO:
                                proxy = sym_avg_price.get(sym, _ZERO)
                            tx_fx = Decimal("1")
                            unit_cost = proxy
                            unit_base = proxy
                            cost_known = proxy > _ZERO
                        if not cost_known:
                            logger.warning(
                                "Unmatched TRANSFER_IN with no recoverable cost basis: "
                                "tx_id=%s %s@%s qty=%s — using zero cost",
                                tx.id,
                                sym,
                                exch,
                                qty,
                            )
                        fifo[key].append(
                            {
                                "qty": qty,
                                "unit_cost": unit_cost,
                                "unit_cost_base": unit_base,
                                "currency": tx_ccy,
                                "fx_rate": tx_fx,
                                "is_paid": cost_known,
                            }
                        )

                elif ttype == TxType.CONVERSION_OUT:
                    src_sym = sym
                    dest_sym, dest_exch, matched_ci_qty, matched_ci_price = _match_conversion_in(tx, src_sym)

                    if dest_sym is None:
                        # B2: Unmatched — preserve cost on source
                        logger.error(
                            "Unmatched CONVERSION_OUT: tx_id=%s src=%s qty=%s "
                            "exchange=%s notes='%s' — cost preserved on source",
                            tx.id,
                            src_sym,
                            qty,
                            exch,
                            tx.notes or "",
                        )
                        # Qty leaves but we DON'T consume cost layers
                        # Just remove zero-cost equivalent from pool for qty tracking
                    else:
                        # O5: Warn if conversion qty exceeds pool
                        pool_qty = sum(ly["qty"] for ly in fifo.get(key, []))

                        # Stablecoin with no tracked history: seed synthetic EUR
                        # layers so the cost basis propagates to the destination.
                        # (e.g. USDC acquired off-platform then converted to PAXG)
                        if pool_qty == _ZERO and is_stablecoin(src_sym):
                            if src_sym.upper() in {"EURC", "EURT"}:
                                eur_per_unit = Decimal("1")
                                layer_ccy = "EUR"
                                fx = Decimal("1")
                            else:
                                # USD-pegged stablecoin: 1 unit ≈ 1 USD → convert to EUR
                                eur_per_unit = Decimal(str(usd_to_target))
                                layer_ccy = "USD"
                                fx = eur_per_unit
                            fifo[key].append(
                                {
                                    "qty": qty,
                                    "unit_cost": eur_per_unit,
                                    "unit_cost_base": Decimal("1"),
                                    "currency": layer_ccy,
                                    "fx_rate": fx,
                                    "is_paid": True,
                                }
                            )
                            pool_qty = qty
                            logger.info(
                                "Seeded synthetic %s layer for stablecoin %s@%s " "qty=%s unit_cost=%s (tx_id=%s)",
                                layer_ccy,
                                src_sym,
                                exch,
                                qty,
                                eur_per_unit,
                                tx.id,
                            )
                        elif qty > pool_qty:
                            logger.warning(
                                "Over-conversion: CONVERSION_OUT qty=%s > pool=%s " "for %s@%s (tx_id=%s)",
                                qty,
                                pool_qty,
                                src_sym,
                                exch,
                                tx.id,
                            )
                        # Consume FIFO layers from source
                        cost_removed = _consume_fifo(key, qty)
                        # Create single layer on destination with propagated cost
                        tx_ccy = (tx.currency or "EUR").upper()
                        tx_fx = Decimal(str(tx.conversion_rate)) if tx.conversion_rate else Decimal("1")
                        if matched_ci_qty > 0 and cost_removed > 0:
                            dest_key: FifoKey = (dest_sym, dest_exch or exch)
                            # Destination cost basis = its market value at conversion
                            # (recorded CONVERSION_IN price). Carrying the source cost
                            # instead let mis-matched/chained conversions concentrate
                            # cost into a shrinking qty and fabricate impossible unit
                            # costs (FIN — runaway cost basis up to ~500k EUR/BTC).
                            dest_unit = _conversion_dest_unit_cost(cost_removed, matched_ci_qty, matched_ci_price)
                            fifo[dest_key].append(
                                {
                                    "qty": matched_ci_qty,
                                    "unit_cost": dest_unit,
                                    "unit_cost_base": dest_unit / tx_fx if tx_fx else dest_unit,
                                    "currency": tx_ccy,
                                    "fx_rate": tx_fx,
                                    "is_paid": True,
                                }
                            )
                        elif matched_ci_qty > 0:
                            # Zero cost source (e.g. airdrop converted)
                            dest_key = (dest_sym, dest_exch or exch)
                            fifo[dest_key].append(
                                {
                                    "qty": matched_ci_qty,
                                    "unit_cost": _ZERO,
                                    "unit_cost_base": _ZERO,
                                    "currency": tx_ccy,
                                    "fx_rate": tx_fx,
                                    "is_paid": False,
                                }
                            )

                elif ttype == TxType.CONVERSION_IN:
                    # B1/M2: Collect fees from CONVERSION_IN
                    fee = Decimal(str(tx.fee or 0))
                    if fee > 0:
                        fee_ccy = (tx.fee_currency or tx.currency or "EUR").upper()
                        portfolio_ccy = currency.upper()
                        if fee_ccy == portfolio_ccy:
                            # Add fee to the last layer of this key if it exists
                            layers = fifo.get(key, [])
                            if layers:
                                last = layers[-1]
                                old_total = last["qty"] * last["unit_cost"]
                                last["unit_cost"] = (old_total + fee) / last["qty"] if last["qty"] > 0 else _ZERO
                            else:
                                # No layer yet — CONVERSION_OUT will create it later;
                                # store fee keyed by (sym, exchange) for post-FIFO application
                                _pending_fee_conversions.append((key, fee, fee_ccy))
                        else:
                            _pending_fee_conversions.append((key, fee, fee_ccy))
                    # Qty already handled by CONVERSION_OUT creating the layer

                elif ttype == TxType.DIVIDEND:
                    # Dividend: cash income — does NOT create new shares.
                    # Record income for Total Return calculation.
                    # tx.price = dividend per share, tx.quantity = shares (or total amount)
                    div_amount = qty * Decimal(str(tx.price or 0))
                    if div_amount > 0:
                        tx_ccy = (tx.currency or "EUR").upper()
                        portfolio_ccy = currency.upper()
                        if tx_ccy != portfolio_ccy and tx.conversion_rate:
                            div_amount *= Decimal(str(tx.conversion_rate))
                        elif tx_ccy != portfolio_ccy:
                            # Will be resolved later with forex rates
                            _pending_fee_conversions.append((f"__div__{sym}", div_amount, tx_ccy))
                            div_amount = _ZERO
                        dividend_income[key] += div_amount

                # STAKING/UNSTAKING: no cost impact (same exchange, same symbol)

            # ---- Derive per-asset invested_map from FIFO layers ----
            # Each asset_id maps to (symbol, exchange) via aid_to_symbol/aid_to_exchange
            sym_to_aids: Dict[str, list] = _defaultdict(list)
            for a in investment_assets:
                sym_to_aids[a.symbol.upper()].append(a)

            # Aggregate cost by (symbol, exchange) from remaining FIFO layers
            cost_by_key: Dict[FifoKey, Decimal] = _defaultdict(lambda: _ZERO)
            paid_qty_by_key: Dict[FifoKey, Decimal] = _defaultdict(lambda: _ZERO)
            fifo_seen_keys: set = set()  # tracks all keys touched by FIFO (incl. zero-cost)
            for fkey, layers in fifo.items():
                if fkey[1].startswith("__transit__"):
                    # DEBUG: log orphan transit layers so we can spot cost basis loss
                    if fkey[0] == "BTC":
                        _orphan_cost = sum(ly["qty"] * ly["unit_cost"] for ly in layers)
                        _orphan_qty = sum(ly["qty"] for ly in layers)
                        if _orphan_qty > 0:
                            logger.warning(
                                "[FIFO_DEBUG] BTC orphan transit %s qty=%s cost=%s layers=%s",
                                fkey[1][:40],
                                _orphan_qty,
                                _orphan_cost,
                                len(layers),
                            )
                    continue  # skip unmatched transit layers
                fifo_seen_keys.add(fkey)
                for layer in layers:
                    cost_by_key[fkey] += layer["qty"] * layer["unit_cost"]
                    if layer["is_paid"]:
                        paid_qty_by_key[fkey] += layer["qty"]
                # DEBUG: log final BTC layers per key
                if fkey[0] == "BTC":
                    _tot_qty = sum(ly["qty"] for ly in layers)
                    _tot_cost = sum(ly["qty"] * ly["unit_cost"] for ly in layers)
                    logger.warning(
                        "[FIFO_DEBUG] BTC final %s qty=%s cost=%s layers=%s detail=%s",
                        fkey[1],
                        _tot_qty,
                        _tot_cost,
                        len(layers),
                        [
                            {
                                "qty": str(ly["qty"]),
                                "unit_cost": str(ly["unit_cost"]),
                                "is_paid": ly.get("is_paid", False),
                            }
                            for ly in layers
                        ],
                    )

            # Also build symbol-level aggregates for PRA and downstream compatibility
            cost_by_sym: Dict[str, Decimal] = _defaultdict(lambda: _ZERO)
            cost_qty_by_sym: Dict[str, Decimal] = _defaultdict(lambda: _ZERO)
            buy_cost_by_sym: Dict[str, Decimal] = _defaultdict(lambda: _ZERO)
            for fkey, cost in cost_by_key.items():
                sym = fkey[0]
                cost_by_sym[sym] += cost
                buy_cost_by_sym[sym] += cost
                cost_qty_by_sym[sym] += paid_qty_by_key.get(fkey, _ZERO)

            # Compute undiluted PRA per symbol: cost / cost-bearing qty
            buy_pra_by_sym: Dict[str, Decimal] = {}
            for sym in cost_by_sym:
                cq = cost_qty_by_sym.get(sym, _ZERO)
                if cq > 0 and cost_by_sym[sym] > 0:
                    buy_pra_by_sym[sym] = cost_by_sym[sym] / cq

            # Map cost to each asset_id using FIFO layers per (symbol, exchange)
            for a in investment_assets:
                aid = str(a.id)
                fkey = (a.symbol.upper(), (a.exchange or "").strip())
                cost = cost_by_key.get(fkey, _ZERO)
                if cost > 0:
                    invested_map[aid] = cost
                elif fkey in fifo_seen_keys:
                    # Zero-cost asset (pure airdrop / staking reward) — must record
                    # _ZERO explicitly so get_asset_metrics doesn't fall back to buy_pra.
                    invested_map[aid] = _ZERO

            # FX gain decomposition per (symbol, exchange):
            # For each layer, FX gain = qty * unit_cost_base * (current_fx - purchase_fx)
            # This is computed later once current forex rates are available.
            # Store the base-currency cost for decomposition.
            fx_base_cost_by_key: Dict[FifoKey, list] = _defaultdict(list)
            for fkey, layers in fifo.items():
                if fkey[1].startswith("__transit__"):
                    continue
                for layer in layers:
                    if layer.get("is_paid") and layer.get("currency") and layer["currency"] != currency.upper():
                        fx_base_cost_by_key[fkey].append(
                            {
                                "qty": layer["qty"],
                                "unit_cost_base": layer.get("unit_cost_base", _ZERO),
                                "currency": layer["currency"],
                                "fx_rate": layer.get("fx_rate", Decimal("1")),
                            }
                        )

        # Apply pending fee/dividend conversions now that FIFO is complete.
        # Fees keyed by (sym, exchange) are added to cost_by_key so they're
        # reflected in invested_map — and therefore in per-asset G/L — before
        # get_asset_metrics() is called below.
        if _pending_fee_conversions:
            portfolio_ccy = currency.upper()
            for entry_key, amount, entry_ccy in _pending_fee_conversions:
                rate, stale = await _get_rate_with_cache(entry_ccy, portfolio_ccy)
                forex_stale = forex_stale or stale
                converted = amount * Decimal(str(rate))

                if isinstance(entry_key, str) and entry_key.startswith("__div__"):
                    real_sym = entry_key[7:]
                    for dkey in dividend_income:
                        if dkey[0] == real_sym:
                            dividend_income[dkey] += converted
                            break
                    continue

                fkey = entry_key  # (sym, exchange)
                cost_by_key[fkey] = cost_by_key.get(fkey, _ZERO) + converted
                cost_by_sym[fkey[0]] = cost_by_sym.get(fkey[0], _ZERO) + converted
                buy_cost_by_sym[fkey[0]] = buy_cost_by_sym.get(fkey[0], _ZERO) + converted

            # Rebuild invested_map and buy_pra_by_sym with fees now included
            for a in investment_assets:
                aid = str(a.id)
                fkey = (a.symbol.upper(), (a.exchange or "").strip())
                cost = cost_by_key.get(fkey, _ZERO)
                if cost > 0:
                    invested_map[aid] = cost
                elif fkey in fifo_seen_keys:
                    invested_map[aid] = _ZERO
            for sym in cost_by_sym:
                cq = cost_qty_by_sym.get(sym, _ZERO)
                if cq > 0 and cost_by_sym[sym] > 0:
                    buy_pra_by_sym[sym] = cost_by_sym[sym] / cq

        # Group assets by type for batch price fetching
        crypto_symbols = [a.symbol for a in investment_assets if a.asset_type == AssetType.CRYPTO]
        stock_symbols = [a.symbol for a in investment_assets if a.asset_type in [AssetType.STOCK, AssetType.ETF]]

        # Fetch prices (with 24h change data) — fallback to DB current_price on timeout
        prices = {}
        price_changes = {}

        # Pre-populate fallback prices from DB (current_price stored on asset)
        db_fallback_prices = {
            a.symbol.upper(): float(a.current_price)
            for a in investment_assets
            if a.current_price and float(a.current_price) > 0
        }

        if crypto_symbols:
            try:
                crypto_prices = await asyncio.wait_for(
                    price_service.get_multiple_crypto_prices(crypto_symbols, currency.lower()),
                    timeout=5.0,
                )
                for symbol, data in crypto_prices.items():
                    prices[symbol.upper()] = data["price"]
                    price_changes[symbol.upper()] = float(data.get("change_percent_24h", 0) or 0)
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(
                    "Crypto price fetch failed (%s), using DB fallback",
                    type(e).__name__,
                )

        if stock_symbols:
            from app.services.market_data_service import market_data_service

            try:
                stock_results = await asyncio.wait_for(
                    market_data_service.get_multiple_stock_prices(stock_symbols),
                    timeout=8.0,
                )
                for symbol, stock_data in stock_results.items():
                    stock_price = stock_data["price"]
                    quote_ccy = stock_data.get("quote_currency", "USD")
                    target = currency.upper()
                    if quote_ccy != target:
                        try:
                            rate = await price_service.get_forex_rate(quote_ccy, target)
                            if rate:
                                stock_price = stock_price * rate
                        except Exception:
                            logger.warning(
                                "Forex %s→%s unavailable for stock %s",
                                quote_ccy,
                                target,
                                symbol,
                            )
                    prices[symbol.upper()] = stock_price
                    price_changes[symbol.upper()] = float(stock_data.get("change_percent_24h", 0) or 0)
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning("Stock price fetch failed (%s), using DB fallback", type(e).__name__)

        # Fill missing prices from DB fallback
        for sym, fallback_price in db_fallback_prices.items():
            if sym not in prices:
                prices[sym] = fallback_price
                price_changes.setdefault(sym, 0.0)

        # Calculate metrics for each investment asset
        total_value = Decimal("0")
        total_invested = Decimal("0")
        asset_metrics = []
        crowdfunding_active = 0
        crowdfunding_completed = 0
        crowdfunding_total_invested = Decimal("0")
        crowdfunding_projected_interest = Decimal("0")
        crowdfunding_next_maturity = None

        for asset in investment_assets:
            # Crowdfunding / real estate with invested_amount: no live price
            is_crowdfunding = asset.asset_type == AssetType.CROWDFUNDING or (
                asset.asset_type == AssetType.REAL_ESTATE and asset.invested_amount is not None
            )

            if is_crowdfunding:
                inv_amount = Decimal(str(asset.invested_amount))
                status = asset.project_status or "active"

                if status == "completed":
                    current_value = Decimal("0")
                    crowdfunding_completed += 1
                else:
                    current_value = inv_amount
                    crowdfunding_active += 1

                crowdfunding_total_invested += inv_amount

                # Projected annual interest
                rate = Decimal(str(asset.interest_rate)) if asset.interest_rate else Decimal("0")
                if status == "active" and rate > 0:
                    crowdfunding_projected_interest += inv_amount * rate / 100

                # Track next maturity
                if status == "active" and asset.maturity_date:
                    if crowdfunding_next_maturity is None or asset.maturity_date < crowdfunding_next_maturity:
                        crowdfunding_next_maturity = asset.maturity_date

                metrics = {
                    "quantity": float(asset.quantity),
                    "avg_buy_price": float(inv_amount),
                    "total_invested": float(inv_amount),
                    "current_price": float(inv_amount) if status != "completed" else 0.0,
                    "current_value": float(current_value),
                    "gain_loss": 0.0,
                    "gain_loss_percent": 0.0,
                }
            else:
                current_price = prices.get(asset.symbol.upper())
                asset_invested = invested_map.get(str(asset.id))
                # Only pass buy_pra when this asset has its own FIFO layers.
                # Using a symbol-wide PRU from a different exchange would give a
                # wrong cost basis for assets with no transactions of their own.
                asset_fkey_check = (
                    asset.symbol.upper(),
                    (asset.exchange or "").strip(),
                )
                asset_buy_pra = buy_pra_by_sym.get(asset.symbol.upper()) if asset_fkey_check in fifo_seen_keys else None
                asset_cump_pru = cump_pru_by_fkey.get(asset_fkey_check)
                # DEBUG: log per-asset inputs for BTC
                if asset.symbol.upper() == "BTC":
                    logger.warning(
                        "[FIFO_DEBUG] BTC asset_inputs exchange=%s qty=%s avg_buy=%s "
                        "asset_invested=%s asset_buy_pra=%s asset_cump_pru=%s",
                        asset.exchange,
                        asset.quantity,
                        asset.avg_buy_price,
                        asset_invested,
                        asset_buy_pra,
                        asset_cump_pru,
                    )
                metrics = await self.get_asset_metrics(
                    asset, current_price, asset_invested, asset_buy_pra, asset_cump_pru
                )
                if asset.symbol.upper() == "BTC":
                    logger.warning(
                        "[FIFO_DEBUG] BTC metrics_output exchange=%s total_invested=%s "
                        "current_value=%s avg_buy_price=%s gain_loss=%s",
                        asset.exchange,
                        metrics.get("total_invested"),
                        metrics.get("current_value"),
                        metrics.get("avg_buy_price"),
                        metrics.get("gain_loss"),
                    )

                # Post-filter: skip dust positions based on actual current value
                if (
                    not include_zero_quantity
                    and metrics["current_value"] < min_value_eur
                    and metrics["total_invested"] < min_value_eur
                ):
                    continue

            total_value += Decimal(str(metrics["current_value"]))
            # Use real invested (from invested_map) for portfolio total,
            # not the PRA-based invested shown per asset
            real_invested = invested_map.get(str(asset.id))
            if real_invested is not None:
                total_invested += real_invested
            else:
                total_invested += Decimal(str(metrics["total_invested"]))

            # Per-asset fees and break-even price.
            # When FIFO is active (asset_invested is not None), transaction fees are
            # already baked into each layer's unit_cost — adding fees_map would
            # double-count them.  The PRA-based fallback path keeps fees separate so
            # they must be added here.
            asset_fees = fees_map.get(str(asset.id), 0.0)
            qty = metrics["quantity"]
            if asset_invested is not None:
                breakeven_price = metrics["total_invested"] / qty if qty > 0 else None
            else:
                breakeven_price = (metrics["total_invested"] + asset_fees) / qty if qty > 0 else None

            # Holding duration and annualized return
            first_date = first_buy_map.get(str(asset.id))
            if first_date and hasattr(first_date, "tzinfo") and first_date.tzinfo is None:
                first_date = first_date.replace(tzinfo=timezone.utc)
            holding_days = (datetime.now(timezone.utc) - first_date).days if first_date else None
            annualized_return = None
            if holding_days and holding_days >= 7 and metrics["total_invested"] > 0 and metrics["current_value"] > 0:
                years = holding_days / 365.25
                ratio = metrics["current_value"] / metrics["total_invested"]
                if ratio > 0 and years > 0:
                    raw = (pow(ratio, 1 / years) - 1) * 100
                    # O4: Clamp to avoid aberrations on short holding periods
                    annualized_return = round(max(-99.0, min(raw, 999.0)), 2)

            # Dividend income for this asset
            asset_fkey = (asset.symbol.upper(), (asset.exchange or "").strip())
            asset_div_income = float(dividend_income.get(asset_fkey, _ZERO)) if inv_asset_ids else 0.0

            asset_entry = {
                "id": str(asset.id),
                "symbol": asset.symbol,
                "name": asset.name,
                "asset_type": asset.asset_type.value,
                "exchange": asset.exchange,
                "change_percent_24h": price_changes.get(asset.symbol.upper(), 0.0),
                "total_fees": asset_fees,
                "breakeven_price": round(breakeven_price, 2) if breakeven_price is not None else None,
                "first_buy_date": first_date.isoformat() if first_date else None,
                "holding_days": holding_days,
                "annualized_return": annualized_return,
                "dividend_income": asset_div_income,
                **metrics,
            }
            # Include crowdfunding fields if present
            if is_crowdfunding:
                asset_entry["interest_rate"] = float(asset.interest_rate) if asset.interest_rate else None
                asset_entry["maturity_date"] = asset.maturity_date.isoformat() if asset.maturity_date else None
                asset_entry["project_status"] = asset.project_status
                asset_entry["invested_amount"] = float(asset.invested_amount) if asset.invested_amount else None

            asset_metrics.append(asset_entry)

        # ---- FX gain decomposition per asset ----
        # For assets bought in foreign currency, split total G/L into:
        #   fx_gain = qty * unit_cost_base * (current_fx - purchase_fx)
        #   asset_gain = total_gain_loss - fx_gain
        fx_gain_by_key: Dict[Tuple[str, str], float] = {}
        _fx_rate_cache: Dict[str, float] = {"USD": usd_to_target, target: 1.0}
        if target != "EUR":
            _fx_rate_cache["EUR"] = eur_to_target
        if inv_asset_ids:
            for fkey, fx_layers in fx_base_cost_by_key.items():
                total_fx_gain = 0.0
                for fl in fx_layers:
                    base_ccy = fl["currency"]
                    purchase_fx = float(fl["fx_rate"])
                    if base_ccy not in _fx_rate_cache:
                        try:
                            rate_val, _ = await _get_rate_with_cache(base_ccy, target)
                            _fx_rate_cache[base_ccy] = rate_val
                        except Exception:
                            _fx_rate_cache[base_ccy] = purchase_fx
                    current_fx = _fx_rate_cache[base_ccy]
                    fx_delta = current_fx - purchase_fx
                    layer_fx_gain = float(fl["qty"]) * float(fl["unit_cost_base"]) * fx_delta
                    total_fx_gain += layer_fx_gain
                fx_gain_by_key[fkey] = total_fx_gain

        # Inject fx_gain and total_return into asset_metrics
        total_dividend_income = 0.0
        for am in asset_metrics:
            akey = (am["symbol"].upper(), (am.get("exchange") or "").strip())
            am["fx_gain"] = round(fx_gain_by_key.get(akey, 0.0), 2)
            am["asset_gain"] = round(am.get("gain_loss", 0.0) - am["fx_gain"], 2)
            div_inc = am.get("dividend_income", 0.0)
            am["total_return"] = round(am.get("gain_loss", 0.0) + div_inc, 2)
            total_dividend_income += div_inc

        # Calculate stablecoin cash value using live market prices
        # This detects depegs (e.g. USDC at $0.87 in March 2023)
        cash_from_stablecoins = Decimal("0")
        stablecoin_list = []
        usd_stablecoins = {
            "USDT",
            "USDC",
            "BUSD",
            "DAI",
            "FDUSD",
            "TUSD",
            "PYUSD",
            "FRAX",
            "LUSD",
            "USDG",
        }
        eur_stablecoins = {"EURC", "EURT"}
        _DEPEG_THRESHOLD = 0.02  # 2% deviation from peg triggers warning

        # Batch-fetch live stablecoin prices from CoinGecko
        stablecoin_symbols = [a.symbol for a in stablecoin_assets]
        stablecoin_live_prices: Dict[str, float] = {}
        if stablecoin_symbols:
            try:
                sc_prices = await asyncio.wait_for(
                    price_service.get_multiple_crypto_prices(stablecoin_symbols, currency.lower()),
                    timeout=5.0,
                )
                for sym, data in sc_prices.items():
                    stablecoin_live_prices[sym.upper()] = float(data["price"])
            except Exception:
                pass  # fallback to peg below

        for asset in stablecoin_assets:
            sym_upper = asset.symbol.upper()
            live_price = stablecoin_live_prices.get(sym_upper)

            if live_price and live_price > 0:
                # Use live market price
                unit_price = live_price
            elif sym_upper in usd_stablecoins:
                unit_price = usd_to_target  # fallback: 1 USD = target rate
            elif sym_upper in eur_stablecoins:
                unit_price = eur_to_target  # fallback: 1 EUR = target rate
            else:
                unit_price = eur_to_target

            value = float(asset.quantity) * unit_price
            if value < min_value_eur:
                continue

            # Detect depeg: compare live price to expected peg value
            depeg_percent = 0.0
            if live_price and live_price > 0:
                if sym_upper in usd_stablecoins:
                    expected_price = usd_to_target
                else:
                    expected_price = eur_to_target
                if expected_price > 0:
                    depeg_percent = abs(live_price - expected_price) / expected_price

            cash_from_stablecoins += Decimal(str(value))
            stablecoin_list.append(
                {
                    "id": str(asset.id),
                    "symbol": asset.symbol,
                    "quantity": float(asset.quantity),
                    "value": value,
                    "unit_price": unit_price,
                    "depeg_warning": depeg_percent > _DEPEG_THRESHOLD,
                    "depeg_percent": round(depeg_percent * 100, 2) if depeg_percent > _DEPEG_THRESHOLD else 0,
                }
            )

        # Calculate fiat cash value
        cash_from_fiat = Decimal("0")
        fiat_list = []
        _fiat_rates = {
            "EUR": eur_to_target,
            "USD": usd_to_target,
            "GBP": 1.0,
            "CHF": 1.0,
        }
        # Fetch additional rates for non-target fiat if needed
        for sym in {"GBP", "CHF"} - {target}:
            try:
                rate = await price_service.get_forex_rate(sym, target)
                if rate:
                    _fiat_rates[sym] = float(rate)
            except Exception:
                pass
        _fiat_rates[target] = 1.0  # target currency = 1:1
        for asset in fiat_assets:
            rate = _fiat_rates.get(asset.symbol.upper(), eur_to_target)
            value = float(asset.quantity) * rate
            cash_from_fiat += Decimal(str(value))
            fiat_list.append(
                {
                    "id": str(asset.id),
                    "symbol": asset.symbol,
                    "quantity": float(asset.quantity),
                    "value": value,
                }
            )

        # Sort by value descending
        asset_metrics.sort(key=lambda x: x["current_value"], reverse=True)

        # Compute risk weights (volatility contribution per symbol)
        symbol_values: Dict[str, float] = {}
        for am in asset_metrics:
            s = am["symbol"].upper()
            symbol_values[s] = symbol_values.get(s, 0) + am["current_value"]
        risk_weights = await self._compute_risk_weights(
            db, list(symbol_values.keys()), symbol_values, float(total_value)
        )
        for am in asset_metrics:
            am["risk_weight"] = risk_weights.get(am["symbol"].upper(), 0.0)

        total_gain_loss = total_value - total_invested
        total_gain_loss_percent = float(total_gain_loss / total_invested * 100) if total_invested > 0 else 0.0

        # Available liquidity = stablecoins + fiat assets + portfolio cash_balances
        available_liquidity = float(cash_from_stablecoins + cash_from_fiat)

        # Total return = capital gain + dividends
        total_return = float(total_gain_loss) + total_dividend_income

        result = {
            "total_value": float(total_value),
            "total_invested": float(total_invested),
            "total_gain_loss": float(total_gain_loss),
            "total_gain_loss_percent": total_gain_loss_percent,
            "total_dividend_income": round(total_dividend_income, 2),
            "total_return": round(total_return, 2),
            "assets_count": len(asset_metrics),
            "assets": asset_metrics,
            "cash_from_stablecoins": float(cash_from_stablecoins),
            "stablecoins": stablecoin_list,
            "cash_from_fiat": float(cash_from_fiat),
            "fiat_assets": fiat_list,
            "available_liquidity": available_liquidity,
            "forex_stale": forex_stale,
        }

        # Include crowdfunding summary if relevant
        if crowdfunding_active > 0 or crowdfunding_completed > 0:
            result["crowdfunding_summary"] = {
                "total_invested": float(crowdfunding_total_invested),
                "active_projects": crowdfunding_active,
                "completed_projects": crowdfunding_completed,
                "projected_annual_interest": float(crowdfunding_projected_interest),
                "next_maturity": crowdfunding_next_maturity.isoformat() if crowdfunding_next_maturity else None,
            }

        return result

    async def _fetch_period_changes(self, symbols_by_type: Dict[str, List[str]], days: int) -> Dict[str, float]:
        """Fetch price change percentage over a period for each symbol.

        Strategy (prioritized):
        1. Cached historical data (Redis/PostgreSQL) — fast, no API calls
        2. CoinGecko batch API for crypto — single call, pre-computed periods
        3. Live historical fetch — last resort, one API call per symbol

        Returns {SYMBOL: change_percent}.
        """
        from app.tasks.history_cache import get_cached_history

        changes: Dict[str, float] = {}
        uncached_crypto: list[str] = []
        uncached_stocks: list[str] = []

        # ── Step 1: Try cached historical data first (no API calls) ──
        all_symbols = []
        for syms in symbols_by_type.values():
            all_symbols.extend(syms)

        for symbol in all_symbols:
            try:
                _dates, prices = get_cached_history(symbol.upper(), days=max(days, 2))
            except Exception:
                prices = []
            if prices and len(prices) >= 2 and prices[0] != 0:
                change = (prices[-1] - prices[0]) / prices[0] * 100
                changes[symbol.upper()] = change
            else:
                # Track uncached symbols by type for live fallback
                sym_upper = symbol.upper()
                if sym_upper in [s.upper() for s in symbols_by_type.get("crypto", [])]:
                    uncached_crypto.append(symbol)
                else:
                    uncached_stocks.append(symbol)

        # If all symbols resolved from cache, return early
        if not uncached_crypto and not uncached_stocks:
            return changes

        # ── Step 2: CoinGecko batch API for uncached crypto ──
        if uncached_crypto:
            import httpx

            from app.core.timeframe import get_coingecko_period

            cg_period, cg_key = get_coingecko_period(days)
            if cg_period is not None:
                try:
                    from app.ml.historical_data import HistoricalDataFetcher as HDF

                    coin_ids = [HDF.SYMBOL_MAP.get(s.upper(), s.lower()) for s in uncached_crypto]
                    headers = {
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "application/json",
                    }
                    coingecko_key = getattr(price_service, "coingecko_api_key", None)
                    if coingecko_key:
                        headers["x-cg-demo-api-key"] = coingecko_key

                    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
                        response = await client.get(
                            "https://api.coingecko.com/api/v3/coins/markets",
                            params={
                                "vs_currency": "eur",
                                "ids": ",".join(coin_ids),
                                "price_change_percentage": cg_period,
                                "per_page": 250,
                            },
                        )
                        response.raise_for_status()
                        data = response.json()
                        id_to_symbol = {v: k for k, v in HDF.SYMBOL_MAP.items()}
                        for coin in data:
                            coin_id = coin.get("id", "")
                            symbol = id_to_symbol.get(coin_id, coin.get("symbol", "").upper())
                            pct = coin.get(cg_key)
                            if pct is None:
                                continue
                            if isinstance(pct, dict):
                                pct = pct.get("eur")
                                if pct is None:
                                    continue
                            changes[symbol.upper()] = float(pct)
                            # Remove from uncached since we got data
                            uncached_crypto = [s for s in uncached_crypto if s.upper() != symbol.upper()]
                except Exception as e:
                    logger.warning("Failed to fetch crypto period changes (batch): %s", e)

        # ── Step 2b: Try PostgreSQL asset_price_history for remaining ──
        remaining = uncached_crypto + uncached_stocks
        if remaining:
            try:
                from app.core.database import AsyncSessionLocal
                from app.models.asset_price_history import AssetPriceHistory

                cutoff = (datetime.now(timezone.utc) - timedelta(days=days + 5)).date()
                sym_uppers = [s.upper() for s in remaining]
                async with AsyncSessionLocal() as _db:
                    # One batched query (WHERE symbol IN ...) instead of one SELECT
                    # per symbol; group the rows by symbol Python-side.
                    result = await _db.execute(
                        select(AssetPriceHistory.symbol, AssetPriceHistory.price_eur)
                        .where(
                            AssetPriceHistory.symbol.in_(sym_uppers),
                            AssetPriceHistory.price_date >= cutoff,
                        )
                        .order_by(AssetPriceHistory.symbol, AssetPriceHistory.price_date)
                    )
                    prices_by_sym: Dict[str, list] = {}
                    for sym, px in result.all():
                        prices_by_sym.setdefault(sym, []).append(float(px))
                    for sym_upper, prices in prices_by_sym.items():
                        if len(prices) >= 2 and prices[0] != 0:
                            changes[sym_upper] = (prices[-1] - prices[0]) / prices[0] * 100
                    remaining = [s for s in remaining if s.upper() not in changes]
            except Exception as e:
                logger.warning("DB period change lookup failed: %s", e)

        # ── Step 3: Live historical fetch for remaining uncached symbols (fast mode) ──
        if remaining:
            fetcher = HistoricalDataFetcher()
            try:
                for symbol in remaining:
                    try:
                        sym_upper = symbol.upper()
                        if sym_upper in [s.upper() for s in symbols_by_type.get("crypto", [])]:
                            _, prices = await fetcher.get_crypto_history(symbol, days=days, fast=True)
                        else:
                            _, prices = await fetcher.get_stock_history(symbol, days=days)
                        if prices and len(prices) >= 2 and prices[0] != 0:
                            change = (prices[-1] - prices[0]) / prices[0] * 100
                            changes[sym_upper] = change
                    except Exception:
                        pass
            finally:
                await fetcher.close()

        return changes

    async def get_user_dashboard_metrics(
        self,
        db: AsyncSession,
        user_id: str,
        currency: str = "EUR",
        days: int = 30,
    ) -> Dict:
        """Cached, single-flight dashboard metrics for a user's entire portfolio.

        The 2-minute in-memory cache is fronted by a per-key single-flight guard:
        when several requests miss the cache at once (e.g. right after the TTL
        expires), only the first recomputes the full FIFO / value series; the rest
        await that same result instead of stampeding the DB and CPU.
        """
        cache_key = (user_id, days, currency)
        now = time.time()
        if cache_key in _dashboard_cache:
            ts, cached = _dashboard_cache[cache_key]
            if now - ts < _DASHBOARD_CACHE_TTL:
                return cached

        # Single-flight: join an in-flight recompute for this key if one exists.
        inflight = _dashboard_inflight.get(cache_key)
        if inflight is not None:
            return await inflight

        fut: "asyncio.Future" = asyncio.get_event_loop().create_future()
        _dashboard_inflight[cache_key] = fut
        try:
            result = await self._compute_user_dashboard_metrics(db, user_id, currency, days)
            _cache_put_dashboard(cache_key, (time.time(), result))
            if not fut.done():
                fut.set_result(result)
            return result
        except BaseException as exc:
            if not fut.done():
                fut.set_exception(exc)
            raise
        finally:
            _dashboard_inflight.pop(cache_key, None)

    async def _compute_user_dashboard_metrics(
        self,
        db: AsyncSession,
        user_id: str,
        currency: str = "EUR",
        days: int = 30,
    ) -> Dict:
        """Full (uncached) dashboard computation. Fronted by get_user_dashboard_metrics."""
        # Get all user portfolios
        result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == user_id,
            )
        )
        portfolios = result.scalars().all()

        if not portfolios:
            return {
                "total_value": 0.0,
                "total_invested": 0.0,
                "net_capital": 0.0,
                "total_gain_loss": 0.0,
                "total_gain_loss_percent": 0.0,
                "net_gain_loss": 0.0,
                "net_gain_loss_percent": 0.0,
                "daily_change": 0.0,
                "daily_change_percent": 0.0,
                "portfolios_count": 0,
                "assets_count": 0,
                "allocation": [],
                "top_performers": [],
                "worst_performers": [],
            }

        # Calculate metrics for each portfolio
        total_value = Decimal("0")
        # pnl_value = total_value + stablecoins + fiat: used only for net_gain_loss.
        # When selling OM→USDT, the USDT is the realized value but excluded from
        # total_value (display-only). Including it here gives a correct all-time P&L.
        pnl_value = Decimal("0")
        total_invested = Decimal("0")
        total_sold = Decimal("0")
        total_realized = Decimal("0")
        total_unrealized = Decimal("0")
        total_pnl_fees = Decimal("0")
        total_liquidity = Decimal("0")
        all_assets = []
        any_forex_stale = False

        for portfolio in portfolios:
            try:
                logger.debug("get_user_dashboard_metrics: processing portfolio %s", portfolio.id)
                portfolio_metrics = await self.get_portfolio_metrics(db, str(portfolio.id), currency)
                logger.debug(
                    "get_user_dashboard_metrics: portfolio_metrics OK, total_value=%.2f",
                    portfolio_metrics.get("total_value", 0),
                )
            except Exception as _pm_exc:
                import traceback as _tb

                logger.error(
                    "get_portfolio_metrics failed for portfolio %s: %s\n%s",
                    portfolio.id,
                    _pm_exc,
                    _tb.format_exc(),
                )
                continue
            try:
                # Get historical total invested (sum of all buy transactions)
                portfolio_history = await self.get_portfolio_history(db, str(portfolio.id), currency)
            except Exception as _ph_exc:
                import traceback as _tb

                logger.error(
                    "get_portfolio_history failed for portfolio %s: %s\n%s",
                    portfolio.id,
                    _ph_exc,
                    _tb.format_exc(),
                )
                portfolio_history = {
                    "total_invested_all_time": 0.0,
                    "total_sold_fiat": 0.0,
                    "realized_gains": 0.0,
                    "total_fees": 0.0,
                }
            total_value += Decimal(str(portfolio_metrics["total_value"]))
            pnl_value += Decimal(str(portfolio_metrics["total_value"]))
            pnl_value += Decimal(str(portfolio_metrics.get("cash_from_stablecoins", 0)))
            pnl_value += Decimal(str(portfolio_metrics.get("cash_from_fiat", 0)))
            total_invested += Decimal(str(portfolio_history["total_invested_all_time"]))
            # Use total_sold_fiat (only SELL, not conversions) for net_capital
            total_sold += Decimal(str(portfolio_history.get("total_sold_fiat", 0)))
            total_realized += Decimal(str(portfolio_history.get("realized_gains", 0)))
            # Unrealized P&L from portfolio_metrics: correctly uses cost basis
            # of CURRENT holdings only (qty * avg_buy_price), not all-time invested
            total_unrealized += Decimal(str(portfolio_metrics["total_gain_loss"]))
            total_pnl_fees += Decimal(str(portfolio_history.get("total_fees", 0)))
            total_liquidity += Decimal(str(portfolio_metrics.get("available_liquidity", 0)))
            # Add portfolio cash_balances (fiat held on exchanges)
            for _ccy, amount in (portfolio.cash_balances or {}).items():
                total_liquidity += Decimal(str(amount))
            all_assets.extend(portfolio_metrics["assets"])
            any_forex_stale = any_forex_stale or portfolio_metrics.get("forex_stale", False)

        # total_gain_loss: same base as net_gain_loss (pnl_value includes stablecoins/fiat)
        total_gain_loss = pnl_value - total_invested
        if total_invested > 0:
            total_gain_loss_percent = float(total_gain_loss / total_invested * 100)
        else:
            total_gain_loss_percent = 0.0

        # Calculate allocation by asset type
        allocation = {}
        for asset in all_assets:
            asset_type = asset["asset_type"]
            if asset_type not in allocation:
                allocation[asset_type] = 0.0
            allocation[asset_type] += asset["current_value"]

        allocation_list = [
            {
                "type": asset_type,
                "value": value,
                "percentage": (value / float(total_value) * 100) if total_value > 0 else 0,
            }
            for asset_type, value in allocation.items()
        ]
        allocation_list.sort(key=lambda x: x["value"], reverse=True)

        # Aggregate assets by symbol (merge duplicates across portfolios)
        symbol_agg: Dict[str, Dict] = {}
        for a in all_assets:
            sym = a["symbol"]
            if sym not in symbol_agg:
                symbol_agg[sym] = {
                    "symbol": sym,
                    "name": a["name"],
                    "asset_type": a["asset_type"],
                    "current_price": a.get("current_price"),
                    "total_invested": 0.0,
                    "current_value": 0.0,
                    "total_quantity": 0.0,
                }
            symbol_agg[sym]["total_invested"] += a["total_invested"]
            symbol_agg[sym]["current_value"] += a["current_value"]
            symbol_agg[sym]["total_quantity"] += a.get("quantity", 0)

        # Fetch period change percentages (batch API call)
        symbols_by_type: Dict[str, List[str]] = {}
        for data in symbol_agg.values():
            at = data["asset_type"]
            symbols_by_type.setdefault(at, []).append(data["symbol"])

        period_changes = await self._fetch_period_changes(symbols_by_type, days)

        # Assign period change for each symbol
        for data in symbol_agg.values():
            sym = data["symbol"].upper()
            if sym in period_changes:
                data["period_change_percent"] = period_changes[sym]
            else:
                # Fallback to gain/loss vs avg buy price
                inv = data["total_invested"]
                data["period_change_percent"] = (data["current_value"] - inv) / inv * 100 if inv > 0 else 0.0

        aggregated = list(symbol_agg.values())

        # Top and worst performers (by price change over selected period)
        top_performers = [a for a in aggregated if a["period_change_percent"] > 0]
        top_performers.sort(key=lambda x: x["period_change_percent"], reverse=True)
        top_performers = top_performers[:5]

        worst_performers = [a for a in aggregated if a["period_change_percent"] < 0]
        worst_performers.sort(key=lambda x: x["period_change_percent"])
        worst_performers = worst_performers[:5]

        # Period change (portfolio-level) — weighted average of asset period changes
        period_change_percent = 0.0
        if float(total_value) > 0 and aggregated:
            for a in aggregated:
                weight = a["current_value"] / float(total_value) if float(total_value) > 0 else 0
                period_change_percent += a.get("period_change_percent", 0) * weight
        period_change = float(total_value) * period_change_percent / 100 if period_change_percent else 0.0

        # Net capital = money injected (BUY) - money withdrawn (SELL to fiat only)
        # CONVERSION_OUT excluded: crypto→crypto swaps don't change capital deployed
        net_capital = total_invested - total_sold

        # Unified P&L: pnl_value includes stablecoins + fiat so that proceeds from
        # selling (e.g. OM→USDT) are counted in the gain/loss, not just investment assets.
        net_gain_loss = pnl_value - total_invested
        if total_invested > 0:
            net_gain_loss_percent = float(net_gain_loss / total_invested * 100)
        else:
            net_gain_loss_percent = 0.0

        result = {
            "total_value": float(total_value),
            "total_invested": float(total_invested),
            "net_capital": float(net_capital),
            "total_gain_loss": float(total_gain_loss),
            "total_gain_loss_percent": total_gain_loss_percent,
            "net_gain_loss": float(net_gain_loss),
            "net_gain_loss_percent": net_gain_loss_percent,
            "daily_change": sum(a["current_value"] * a.get("change_percent_24h", 0) / 100 for a in all_assets),
            "daily_change_percent": (
                sum((a["current_value"] / float(total_value)) * a.get("change_percent_24h", 0) for a in all_assets)
                if float(total_value) > 0
                else 0.0
            ),
            "period_change": period_change,
            "period_change_percent": period_change_percent,
            "portfolios_count": len(portfolios),
            "assets_count": len({a["symbol"] for a in all_assets}),
            "allocation": allocation_list,
            "top_performers": [
                {
                    "symbol": a["symbol"],
                    "name": a["name"],
                    "asset_type": a["asset_type"],
                    "gain_loss_percent": round(a["period_change_percent"], 2),
                    "current_value": a["current_value"],
                }
                for a in top_performers
            ],
            "worst_performers": [
                {
                    "symbol": a["symbol"],
                    "name": a["name"],
                    "asset_type": a["asset_type"],
                    "gain_loss_percent": round(a["period_change_percent"], 2),
                    "current_value": a["current_value"],
                }
                for a in worst_performers
            ],
            "available_liquidity": float(total_liquidity),
            "period_changes": period_changes,
            # Pre-built asset allocation (avoids N+1 re-fetch in dashboard endpoint)
            "aggregated_assets": [
                {
                    "symbol": a["symbol"],
                    "name": a["name"],
                    "asset_type": a["asset_type"],
                    "current_value": a["current_value"],
                    "total_invested": a["total_invested"],
                    "avg_buy_price": (a["total_invested"] / a["total_quantity"] if a["total_quantity"] > 0 else 0.0),
                    "gain_loss_percent": round(a.get("period_change_percent", 0), 2),
                    "percentage": round(
                        (a["current_value"] / float(total_value) * 100) if float(total_value) > 0 else 0,
                        2,
                    ),
                }
                for a in aggregated
                if a["current_value"] > 0
            ],
            # P&L breakdown: always all-time, unified on the same root as net_gain_loss.
            # total_pnl = total_value - total_invested (single source of truth)
            # unrealized = total_pnl - realized (residual, ensures perfect reconciliation)
            # Guarantee: realized + unrealized = total_pnl (by construction)
            # net_pnl = total_pnl - fees (fees deducted exactly once)
            "pnl_data": {
                "realized_pnl": float(total_realized),
                "unrealized_pnl": float((total_value - total_invested) - total_realized),
                "total_pnl": float(total_value - total_invested),
                "total_fees": float(total_pnl_fees),
                "net_pnl": float(total_value - total_invested - total_pnl_fees),
                "is_all_time": True,  # P&L breakdown is always cumulative
            },
            "forex_stale": any_forex_stale,
        }

        return result

    async def get_portfolio_history(self, db: AsyncSession, portfolio_id: str, currency: str = "EUR") -> Dict:
        """
        Calculate historical investment metrics for a portfolio.
        Includes all assets (even those with 0 quantity) and calculates
        total invested from all buy transactions.
        """
        # Get ALL assets in portfolio (including zero quantity), excluding CROWDFUNDING
        result = await db.execute(
            select(Asset).where(
                Asset.portfolio_id == portfolio_id,
                Asset.asset_type != AssetType.CROWDFUNDING,
            )
        )
        all_assets = result.scalars().all()
        asset_ids = [a.id for a in all_assets]

        if not asset_ids:
            return {
                "total_invested_all_time": 0.0,
                "total_sold": 0.0,
                "total_fees": 0.0,
                "realized_gains": 0.0,
                "current_holdings_count": 0,
                "sold_assets_count": 0,
                "sold_assets": [],
            }

        # Get all transactions for these assets
        result = await db.execute(
            select(Transaction)
            .where(
                Transaction.asset_id.in_(asset_ids),
            )
            .order_by(Transaction.executed_at.desc())
        )
        transactions = result.scalars().all()

        # Calculate totals per asset
        asset_history = {}
        for asset in all_assets:
            asset_history[str(asset.id)] = {
                "id": str(asset.id),
                "symbol": asset.symbol,
                "name": asset.name,
                "asset_type": asset.asset_type.value,
                "exchange": asset.exchange,
                "current_quantity": float(asset.quantity),
                "total_bought": Decimal("0"),
                "total_bought_value": Decimal("0"),
                "total_bought_with_cost": Decimal("0"),  # Only transactions with price > 0
                "total_bought_cost_value": Decimal("0"),  # Only transactions with price > 0
                "total_bought_fiat_value": Decimal("0"),  # Only BUY+TRANSFER_IN (real money in, not conversions)
                "total_sold": Decimal("0"),
                "total_sold_value": Decimal("0"),
                "total_sold_fiat_value": Decimal("0"),  # Only SELL (crypto→fiat, real money out)
                "total_fees": Decimal("0"),
                "first_transaction": None,
                "last_transaction": None,
            }

        # Build historical price lookup for transactions with price=0
        # Collect (symbol, date) pairs that need pricing
        from app.models.asset_price_history import AssetPriceHistory

        asset_id_to_symbol = {str(a.id): a.symbol.upper() for a in all_assets}
        price_lookup_needed: set = set()
        for tx in transactions:
            if Decimal(str(tx.price)) == 0 and tx.executed_at is not None:
                sym = asset_id_to_symbol.get(str(tx.asset_id))
                if sym:
                    price_lookup_needed.add((sym, tx.executed_at.date()))

        # Batch fetch from AssetPriceHistory
        historical_prices: dict = {}  # (symbol, date) → price_eur
        if price_lookup_needed:
            symbols_needed = list({s for s, _ in price_lookup_needed})
            dates_needed = list({d for _, d in price_lookup_needed})
            price_result = await db.execute(
                select(
                    AssetPriceHistory.symbol,
                    AssetPriceHistory.price_date,
                    AssetPriceHistory.price_eur,
                ).where(
                    AssetPriceHistory.symbol.in_(symbols_needed),
                    AssetPriceHistory.price_date.in_(dates_needed),
                )
            )
            for row in price_result.all():
                historical_prices[(row[0], row[1])] = Decimal(str(row[2]))

        def _resolve_price(tx, symbol: str) -> Decimal:
            """Get transaction price in the PORTFOLIO currency (EUR).

            The stored ``tx.price`` is denominated in the transaction currency, so
            it is converted via ``conversion_rate`` (EUR per 1 unit of tx currency;
            defaults to 1 for same-currency trades). The historical fallback
            (``AssetPriceHistory.price_eur``) is already EUR and used as-is.
            """
            p = Decimal(str(tx.price))
            if p > 0:
                fx = Decimal(str(tx.conversion_rate)) if tx.conversion_rate else Decimal("1")
                return p * fx
            if tx.executed_at is not None:
                hist_p = historical_prices.get((symbol, tx.executed_at.date()))
                if hist_p:
                    return hist_p
            return Decimal("0")

        # Process transactions
        for tx in transactions:
            asset_id = str(tx.asset_id)
            if asset_id not in asset_history:
                continue

            ah = asset_history[asset_id]
            tx_type = tx.transaction_type.value.upper()
            symbol = asset_id_to_symbol.get(asset_id, "")

            # Track dates (skip if executed_at is None)
            tx_date = tx.executed_at
            if tx_date is not None:
                if ah["last_transaction"] is None or tx_date > ah["last_transaction"]:
                    ah["last_transaction"] = tx_date
                if ah["first_transaction"] is None or tx_date < ah["first_transaction"]:
                    ah["first_transaction"] = tx_date

            # Track fees — FEE-type transactions use quantity*price as the fee amount,
            # so we do NOT also add tx.fee for them (would double-count)
            if tx_type == "FEE":
                ah["total_fees"] += Decimal(str(tx.quantity)) * Decimal(str(tx.price))
            else:
                ah["total_fees"] += Decimal(str(tx.fee or 0))

            # Track buys (including dividend/interest which add quantity)
            if tx_type in [
                "BUY",
                "TRANSFER_IN",
                "AIRDROP",
                "STAKING_REWARD",
                "CONVERSION_IN",
                "DIVIDEND",
                "INTEREST",
            ]:
                original_price = Decimal(str(tx.price))  # tx currency
                # Real capital in is tracked in the portfolio currency (EUR), so
                # convert the stored price via the FX rate captured at execution.
                tx_fx = Decimal(str(tx.conversion_rate)) if tx.conversion_rate else Decimal("1")
                original_price_eur = original_price * tx_fx
                resolved_price = _resolve_price(tx, symbol)
                tx_qty = Decimal(str(tx.quantity))
                ah["total_bought"] += tx_qty
                ah["total_bought_value"] += tx_qty * resolved_price
                # Cost basis: use resolved price (includes historical market value
                # at time of receipt for airdrops/rewards — needed for realized P&L)
                if resolved_price > 0:
                    ah["total_bought_with_cost"] += tx_qty
                    ah["total_bought_cost_value"] += tx_qty * resolved_price
                # Real money in (only BUY with ORIGINAL stored price > 0)
                # Airdrops/rewards/conversions are NOT capital outflow
                # TRANSFER_IN excluded: could be from own wallet (not new capital)
                if tx_type == "BUY" and original_price > 0:
                    ah["total_bought_fiat_value"] += tx_qty * original_price_eur

            # Track sells (real capital out)
            # TRANSFER_OUT excluded: user still owns the asset on cold wallet
            # CONVERSION_OUT included: user disposed of the asset (even if swapped to another crypto),
            #   so it should appear in history as quantity sold
            elif tx_type in ["SELL", "CONVERSION_OUT"]:
                tx_price = _resolve_price(tx, symbol)
                tx_qty = Decimal(str(tx.quantity))
                ah["total_sold"] += tx_qty
                ah["total_sold_value"] += tx_qty * tx_price
                # Track real fiat outflow (only SELL = crypto→fiat)
                # CONVERSION_OUT is crypto→crypto, not actual capital withdrawal
                if tx_type == "SELL":
                    ah["total_sold_fiat_value"] += tx_qty * tx_price

        # Calculate summary metrics
        total_invested_all_time = Decimal("0")
        total_sold_value = Decimal("0")
        total_sold_fiat = Decimal("0")  # Only SELL (crypto→fiat)
        total_fees = Decimal("0")
        current_holdings = []
        sold_assets = []

        for asset_id, ah in asset_history.items():
            # Exclude stablecoins/fiat from investment totals
            if is_cash_like(ah["symbol"]):
                continue
            # total_invested: only count BUY transactions (real money in)
            # CONVERSION_IN is a form change (crypto→crypto), not new capital
            total_invested_all_time += ah["total_bought_fiat_value"]
            total_sold_value += ah["total_sold_value"]
            total_sold_fiat += ah["total_sold_fiat_value"]
            total_fees += ah["total_fees"]

            # Format for output
            # Realized gain based on fiat cost basis (money out of pocket)
            # Consistent with "Total investi" which only shows BUY fiat
            if ah["total_bought_fiat_value"] > 0 and ah["total_sold"] > 0 and ah["total_bought"] > 0:
                # Proportional fiat cost: spread BUY cost across total quantity
                # (includes airdrops/conversions which dilute average cost)
                proportional_fiat_cost = ah["total_bought_fiat_value"] * ah["total_sold"] / ah["total_bought"]
                realized_gain_val = float(ah["total_sold_value"] - proportional_fiat_cost)
            elif ah["total_sold"] > 0:
                # No fiat invested (all airdrops/conversions) → pure profit
                realized_gain_val = float(ah["total_sold_value"])
            else:
                realized_gain_val = 0.0

            asset_data = {
                "id": ah["id"],
                "symbol": ah["symbol"],
                "name": ah["name"],
                "asset_type": ah["asset_type"],
                "exchange": ah["exchange"],
                "current_quantity": ah["current_quantity"],
                "total_bought": float(ah["total_bought"]),
                "total_bought_value": float(ah["total_bought_fiat_value"]),
                "total_sold": float(ah["total_sold"]),
                "total_sold_value": float(ah["total_sold_value"]),
                "total_fees": float(ah["total_fees"]),
                "realized_gain": realized_gain_val,
                "first_transaction": ah["first_transaction"].isoformat() if ah["first_transaction"] else None,
                "last_transaction": ah["last_transaction"].isoformat() if ah["last_transaction"] else None,
            }

            # Consider as "sold" only if quantity is ~0 AND has actual sells/conversions
            # Assets only transferred out (no sells) stay in current_holdings
            if ah["current_quantity"] <= 0 and ah["total_sold"] > 0:
                sold_assets.append(asset_data)
            elif ah["current_quantity"] <= 0:
                # Zero quantity but no sells (transferred out only) — skip from history
                continue
            elif ah["total_sold"] > 0:
                # Partially sold: estimate remaining value
                est_value = (
                    float(ah["current_quantity"]) * float(ah["total_bought_value"] / ah["total_bought"])
                    if ah["total_bought"] > 0 and ah["total_bought_value"] > 0
                    else float(ah["current_quantity"])
                )
                if est_value < 0.10:
                    sold_assets.append(asset_data)
                else:
                    current_holdings.append(asset_data)
            else:
                current_holdings.append(asset_data)

        # Sort by total invested (fiat value)
        sold_assets.sort(key=lambda x: x["total_bought_value"], reverse=True)

        # Sum realized gains from individual assets (already computed per-asset)
        total_realized_gains = sum(Decimal(str(a["realized_gain"])) for a in current_holdings + sold_assets)

        return {
            "total_invested_all_time": float(total_invested_all_time),
            "total_sold": float(total_sold_value),
            "total_sold_fiat": float(total_sold_fiat),  # Only SELL (not conversions)
            "total_fees": float(total_fees),
            "realized_gains": float(total_realized_gains),
            "current_holdings_count": len(current_holdings),
            "sold_assets_count": len(sold_assets),
            "sold_assets": sold_assets,
        }

    async def calculate_roi(self, total_invested: Decimal, current_value: Decimal) -> float:
        """Calculate Return on Investment."""
        if total_invested <= 0:
            return 0.0
        return float((current_value - total_invested) / total_invested * 100)

    async def calculate_cagr(
        self,
        initial_value: Decimal,
        final_value: Decimal,
        years: float,
    ) -> float:
        """Calculate Compound Annual Growth Rate (clamped -99% to +999%)."""
        if initial_value <= 0 or years <= 0:
            return 0.0
        raw = (pow(float(final_value / initial_value), 1 / years) - 1) * 100
        return float(max(-99.0, min(raw, 999.0)))


# Singleton instance
metrics_service = MetricsService()
