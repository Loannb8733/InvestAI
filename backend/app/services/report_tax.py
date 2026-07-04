"""French 2086 capital-gains tax computation (art. 150 VH bis CGI).

Extracted from report_service to isolate the money-critical tax replay + formula
from the ~1500 lines of PDF/Excel generation. ``ReportService`` mixes in
``TaxComputeMixin``; the tax PDF/Excel *renderers* stay in report_service and
call ``self.compute_tax_2086`` via the mixin. report_service re-exports the
public tax symbols for backwards compatibility.
"""

from __future__ import annotations

import logging
from collections import defaultdict as _defaultdict
from dataclasses import dataclass, field
from datetime import date as _date
from datetime import datetime
from datetime import timezone as _tz
from decimal import Decimal
from typing import Dict, List, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset, AssetType
from app.models.asset_price_history import AssetPriceHistory
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction, TransactionType
from app.services import fifo_replay

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")
FifoKey = Tuple[str, str]


@dataclass
class TaxEvent2086:
    """Single taxable event (cession) per formulaire 2086."""

    date: datetime
    symbol: str
    event_type: str  # "sell" / "conversion_out"
    quantity: float
    unit_price: float
    cession_price: float  # qty × price − fees
    portfolio_value: float  # valeur globale du portefeuille au moment de la cession
    total_acquisition_cost: float  # coût total d'acquisition cumulé
    acquisition_fraction: float  # total_acq × (cession / portfolio_value)
    gain_loss: float  # cession_price − acquisition_fraction
    holding_period: str  # "court_terme" / "long_terme"
    fees: float


@dataclass
class TaxSummary2086:
    """Full tax summary for one fiscal year."""

    year: int
    total_cessions: float
    total_acquisitions_fraction: float
    total_plus_values: float
    total_moins_values: float
    net_plus_value: float
    nb_cessions: int
    nb_court_terme: int
    nb_long_terme: int
    flat_tax_30: float  # PFU total
    ir_12_8: float  # Impôt sur le revenu (12.8%)
    ps_17_2: float  # Prélèvements sociaux (17.2%)
    events: List[TaxEvent2086] = field(default_factory=list)


@dataclass(frozen=True)
class _TaxMode:
    """A tax-replay mode = a fifo_replay config + whether to canonically sort.

    Two modes exist so the convergence of the 2086's accidental bugs can be
    shadow-compared on real data (scripts/shadow_tax_2086.py) before it is
    trusted. The *legitimate* tax semantics (zero-basis rewards, carried
    conversion cost / sursis d'imposition, zero-basis unproven transfers,
    tx-currency fees) are identical in both modes; only the four accidental
    divergences differ.
    """

    config: "fifo_replay.ReplayConfig"
    canonical_sort: bool


# Legitimate tax semantics — shared by both modes.
_TAX_BASE = dict(
    portfolio_currency="EUR",
    reward_basis=fifo_replay.RewardBasis.ZERO,
    conversion_dest_basis=fifo_replay.ConversionDestBasis.CARRY_COST,
    unmatched_transfer_in=fifo_replay.UnmatchedTransferInPolicy.ZERO,
    fee_handling=fifo_replay.FeeHandling.TX_CURRENCY,
    seed_stablecoin_layers=False,
    skip_null_executed_at=True,
)

# Frozen historical behaviour — the four accidental 2086 bugs kept as-is:
# nondeterministic SQL ordering, no external_id conversion match, no transfer
# network-fee trim, and unmatched CONVERSION_OUT consumed + taxed.
TAX_MODE_LEGACY = _TaxMode(
    config=fifo_replay.ReplayConfig(
        **_TAX_BASE,
        unmatched_conversion_out=fifo_replay.UnmatchedConversionOutPolicy.CONSUME,
        trim_transfer_network_fee=False,
        conversion_external_id_fallback=False,
    ),
    canonical_sort=False,
)

# Converged — the four accidental bugs fixed: deterministic ordering
# (TRANSFER_OUT before same-timestamp TRANSFER_IN), external_id conversion
# match fallback, network-fee trim, and unmatched CONVERSION_OUT preserved
# (a crypto-to-crypto swap is in sursis, not a taxable disposal).
TAX_MODE = _TaxMode(
    config=fifo_replay.ReplayConfig(
        **_TAX_BASE,
        unmatched_conversion_out=fifo_replay.UnmatchedConversionOutPolicy.PRESERVE,
        trim_transfer_network_fee=True,
        conversion_external_id_fallback=True,
    ),
    canonical_sort=True,
)


class TaxComputeMixin:
    """Mixed into ReportService — the 2086 tax computation."""

    async def _get_historical_prices(
        self,
        db: AsyncSession,
        symbols: List[str],
        price_date: _date,
    ) -> Dict[str, Decimal]:
        """Fetch historical EUR prices from asset_price_history for a set of
        symbols on a given date. Falls back to the nearest earlier date within
        7 days if an exact match is missing.
        """
        from datetime import timedelta

        if not symbols:
            return {}

        # Try exact date first
        result = await db.execute(
            select(AssetPriceHistory.symbol, AssetPriceHistory.price_eur).where(
                AssetPriceHistory.symbol.in_(symbols),
                AssetPriceHistory.price_date == price_date,
            )
        )
        prices: Dict[str, Decimal] = {row[0].upper(): Decimal(str(row[1])) for row in result.all()}

        # For missing symbols, look back up to 7 days
        missing = [s for s in symbols if s.upper() not in prices]
        if missing:
            fallback_start = price_date - timedelta(days=7)
            fb_result = await db.execute(
                select(
                    AssetPriceHistory.symbol,
                    AssetPriceHistory.price_eur,
                    AssetPriceHistory.price_date,
                )
                .where(
                    AssetPriceHistory.symbol.in_(missing),
                    AssetPriceHistory.price_date.between(fallback_start, price_date),
                )
                .order_by(
                    AssetPriceHistory.symbol,
                    AssetPriceHistory.price_date.desc(),
                )
            )
            seen = set()
            for row in fb_result.all():
                sym_upper = row[0].upper()
                if sym_upper not in seen:
                    prices[sym_upper] = Decimal(str(row[1]))
                    seen.add(sym_upper)

        return prices

    async def compute_tax_2086(
        self,
        db: AsyncSession,
        user_id: str,
        year: int,
        *,
        mode: _TaxMode = TAX_MODE,
    ) -> TaxSummary2086:
        """Compute capital gains per French 2086 formula (art. 150 VH bis CGI).

        Uses FIFO layers (aligned with metrics_service) with acquisition dates
        for accurate holding-period determination.

        Formula per cession:
          PV = Prix_cession − (Total_acquisition × Prix_cession / Valeur_portefeuille)

        Where:
          - Prix_cession = qty × price − fees
          - Total_acquisition = cumulative PAID cost (BUY + CONVERSION_IN propagated),
            excluding TRANSFER_IN/OUT (no cost impact)
          - Valeur_portefeuille = sum(holdings × market_price) from asset_price_history
        """
        empty = TaxSummary2086(
            year=year,
            total_cessions=0,
            total_acquisitions_fraction=0,
            total_plus_values=0,
            total_moins_values=0,
            net_plus_value=0,
            nb_cessions=0,
            nb_court_terme=0,
            nb_long_terme=0,
            flat_tax_30=0,
            ir_12_8=0,
            ps_17_2=0,
            events=[],
        )

        # 1. Get ALL crypto assets for this user
        result = await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))
        portfolios = result.scalars().all()
        portfolio_ids = [p.id for p in portfolios]
        if not portfolio_ids:
            return empty

        asset_result = await db.execute(select(Asset).where(Asset.portfolio_id.in_(portfolio_ids)))
        assets = asset_result.scalars().all()
        crypto_assets = [a for a in assets if a.asset_type == AssetType.CRYPTO]
        crypto_asset_ids = [a.id for a in crypto_assets]
        if not crypto_asset_ids:
            return empty

        asset_map = {a.id: a for a in crypto_assets}
        aid_to_symbol: Dict[str, str] = {str(a.id): a.symbol.upper() for a in crypto_assets}

        # 2. Get ALL transactions (all years) chronologically
        trans_result = await db.execute(
            select(Transaction)
            .where(Transaction.asset_id.in_(crypto_asset_ids))
            .order_by(Transaction.executed_at.asc())
        )
        all_transactions = list(trans_result.scalars().all())

        # ── 3. Single-pass chronological FIFO replay (unified engine) ─────
        # Layer bookkeeping is delegated to app.services.fifo_replay with the
        # 2086 configuration: zero-basis rewards, carried conversion cost
        # (sursis d'imposition), zero-basis unmatched transfers, tx-currency
        # fees, and the historical behaviours frozen as-is (unmatched
        # CONVERSION_OUT consumed + taxed, no network-fee trim, no external_id
        # match fallback). The art. 150 VH bis ledger and TaxEvent2086
        # construction stay in this module via the on_event callback.
        total_acquisition_cost = _ZERO

        year_start = datetime(year, 1, 1, tzinfo=_tz.utc)
        year_end = datetime(year, 12, 31, 23, 59, 59, tzinfo=_tz.utc)
        events: List[TaxEvent2086] = []
        cession_dates: set = set()

        TxType = TransactionType

        _tax_cfg = mode.config
        # Ordering: the converged mode uses the canonical deterministic order
        # (TRANSFER_OUT before same-timestamp TRANSFER_IN, str(id) tie-break);
        # the legacy mode keeps the bare SQL executed_at order. BOTH passes
        # below must iterate the same order so pass-2 event matching aligns.
        replay_txs = fifo_replay.sort_transactions(all_transactions) if mode.canonical_sort else all_transactions

        def _on_replay_event(ev: fifo_replay.ReplayEvent) -> None:
            nonlocal total_acquisition_cost
            if ev.kind == "BUY":
                total_acquisition_cost += ev.total_cost
                return
            if ev.kind == "CONVERSION_IN_FEE":
                total_acquisition_cost += ev.fee
                return
            if ev.kind not in ("SELL", "CONVERSION_OUT"):
                return
            total_acquisition_cost -= ev.cost_removed
            if ev.kind == "CONVERSION_OUT":
                # B3: a matched conversion's consumed cost re-enters the global
                # acquisition ledger as the new asset's basis.
                total_acquisition_cost += ev.dest_cost
            tx_dt = ev.tx_dt
            if year_start <= tx_dt <= year_end:
                cession_dates.add(tx_dt.date())
                cession_price = ev.quantity * ev.price - ev.fee
                events.append(
                    TaxEvent2086(
                        date=ev.tx.executed_at,
                        symbol=ev.symbol,
                        # Historical parity: the 2086 stores the enum VALUE
                        # (lowercase, e.g. "conversion_out"), not the engine kind.
                        event_type=ev.tx.transaction_type.value,
                        quantity=float(ev.quantity),
                        unit_price=float(ev.price),
                        cession_price=float(cession_price),
                        portfolio_value=0.0,  # filled in pass 2
                        total_acquisition_cost=float(total_acquisition_cost),
                        acquisition_fraction=0.0,  # filled in pass 2
                        gain_loss=0.0,  # filled in pass 2
                        holding_period=(
                            "long_terme"
                            if ev.oldest_acquired_at and (tx_dt - ev.oldest_acquired_at).days >= 730
                            else "court_terme"
                        ),
                        fees=float(ev.fee),
                    )
                )

        fifo_replay.replay(replay_txs, aid_to_symbol, _tax_cfg, on_event=_on_replay_event)

        # ── 4. Pass 2: Compute portfolio_value from historical prices (B1) ──
        # Collect ALL symbols that ever had holdings (we need to replay
        # holdings per cession date, including symbols sold since).
        all_symbols_ever = set(aid_to_symbol.values())

        # Fetch historical prices for all cession dates in batch
        price_cache: Dict[_date, Dict[str, Decimal]] = {}
        for d in cession_dates:
            price_cache[d] = await self._get_historical_prices(
                db,
                list(all_symbols_ever),
                d,
            )

        # Replay holdings to get state at each cession date, then fill events.
        # We need to re-walk transactions to snapshot holdings at each event.
        holdings_replay: Dict[str, Decimal] = _defaultdict(lambda: _ZERO)
        event_idx = 0

        for tx in replay_txs:  # same order as pass 1 so event matching aligns
            asset = asset_map.get(tx.asset_id)
            if not asset or not tx.executed_at:
                continue

            sym = asset.symbol.upper()
            qty = Decimal(str(tx.quantity))
            ttype = tx.transaction_type
            tx_dt = tx.executed_at
            if tx_dt.tzinfo is None:
                tx_dt = tx_dt.replace(tzinfo=_tz.utc)

            # Update replay holdings
            if ttype in (
                TxType.BUY,
                TxType.AIRDROP,
                TxType.STAKING_REWARD,
                TxType.TRANSFER_IN,
                TxType.CONVERSION_IN,
            ):
                holdings_replay[sym] += qty
            elif ttype in (TxType.SELL, TxType.TRANSFER_OUT, TxType.CONVERSION_OUT):
                holdings_replay[sym] = max(_ZERO, holdings_replay[sym] - qty)

            # Check if this tx corresponds to the next event
            is_in_year = year_start <= tx_dt <= year_end
            is_taxable = ttype in (TxType.SELL, TxType.CONVERSION_OUT)
            if is_in_year and is_taxable and event_idx < len(events):
                ev = events[event_idx]
                # Verify match (same date + symbol)
                if ev.date == tx.executed_at and ev.symbol == sym:
                    td = tx_dt.date()
                    day_prices = price_cache.get(td, {})

                    # B1: Compute real portfolio value from market prices
                    portfolio_value = _ZERO
                    for held_sym, held_qty in holdings_replay.items():
                        if held_qty > _ZERO:
                            if held_sym == sym:
                                # Use actual cession price per unit, converted to EUR
                                # (portfolio currency) so it matches the historical
                                # prices used for the other held symbols below.
                                _sell_fx = Decimal(str(tx.conversion_rate)) if tx.conversion_rate else Decimal("1")
                                portfolio_value += held_qty * Decimal(str(tx.price or 0)) * _sell_fx
                            else:
                                hist_price = day_prices.get(held_sym.upper(), _ZERO)
                                portfolio_value += held_qty * hist_price

                    # Apply 2086 formula
                    cession_d = Decimal(str(ev.cession_price))
                    total_acq_d = Decimal(str(ev.total_acquisition_cost))
                    if portfolio_value > 0:
                        acq_fraction = float(total_acq_d * cession_d / portfolio_value)
                    else:
                        acq_fraction = 0.0

                    ev.portfolio_value = float(portfolio_value)
                    ev.acquisition_fraction = acq_fraction
                    ev.gain_loss = ev.cession_price - acq_fraction

                    event_idx += 1

        # ── 5. Build summary ──────────────────────────────────────────
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

    # ── Performance PDF ─────────────────────────────────────────────
