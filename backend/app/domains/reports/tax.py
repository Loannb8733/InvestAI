import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.portfolio.models import Asset, AssetType, Portfolio
from app.domains.reports.tax_ledger import CessionLines, PortfolioLedger
from app.domains.reports.tax_rates import EXEMPTION_THRESHOLD, PfuRates, pfu_rates
from app.domains.reports.tax_valuation import (
    Holdings,
    PriceCache,
    historical_prices,
    holdings_before_sales,
    portfolio_value,
)
from app.domains.transactions.cost_basis import config as replay_config
from app.domains.transactions.cost_basis.replay import replay, sort_transactions
from app.domains.transactions.models import Transaction

_LONG_TERM_DAYS = 730
_CENT = Decimal("0.01")


@dataclass
class TaxEvent2086:
    """Cession imposable, lignes du 2086 en EUR.

    cession_price = l. 218 (net de frais), gross_cession_price = l. 217, fees = l. 214, portfolio_value = l. 212,
    acquisition_cost_gross = l. 220, prior_fractions = l. 221, total_acquisition_cost = l. 223 (PTA net avant la
    cession), acquisition_fraction = l. 223 * l. 217 / l. 212, gain_loss = l. 218 - acquisition_fraction.
    """

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
    gross_cession_price: float = 0.0
    acquisition_cost_gross: float = 0.0
    prior_fractions: float = 0.0


@dataclass
class TaxSummary2086:
    """Récapitulatif annuel : total_cessions = l. 51, net_plus_value = l. 52, PFU selon l'année des revenus.

    exempt : total des prix de cession inférieur ou égal à 305 € (art. 150 VH bis II-B), PFU nul.
    """

    year: int
    total_cessions: float
    total_acquisitions_fraction: float
    total_plus_values: float
    total_moins_values: float
    net_plus_value: float
    nb_cessions: int
    nb_court_terme: int
    nb_long_terme: int
    pfu_total: float
    pfu_ir: float
    pfu_ps: float
    exempt: bool = False
    events: list[TaxEvent2086] = field(default_factory=list)
    rates: PfuRates = field(init=False)

    def __post_init__(self) -> None:
        self.rates = pfu_rates(self.year)

    @property
    def taxable_plus_value(self) -> float:
        """Base du PFU : plus-value nette positive d'une année non exonérée."""
        return 0.0 if self.exempt else max(0.0, self.net_plus_value)

    @property
    def flat_tax_30(self) -> float:
        """Alias déprécié de pfu_total, gardé pour l'API et les scripts : le taux n'est plus 30 % dès 2025."""
        return self.pfu_total

    @property
    def ir_12_8(self) -> float:
        """Alias déprécié de pfu_ir."""
        return self.pfu_ir

    @property
    def ps_17_2(self) -> float:
        """Alias déprécié de pfu_ps : les prélèvements sociaux sont à 18,6 % dès les revenus 2025."""
        return self.pfu_ps


@dataclass(frozen=True)
class TaxMode:
    """Rejeu fiscal : TAX_MODE corrige les divergences accidentelles du rejeu que TAX_MODE_LEGACY fige pour comparaison.

    Legacy : ordre SQL brut au lieu de TRANSFER_OUT avant TRANSFER_IN simultané, pas de repli external_id pour les
    conversions, frais réseau des transferts non rognés, CONVERSION_OUT non apparié consommé. Le 2086 ne dépend plus
    des couches FIFO (seulement la durée de détention indicative) : les deux modes ne diffèrent que par l'ordre.
    """

    config: replay_config.ReplayConfig
    canonical_sort: bool


def _tax_mode(converged: bool) -> TaxMode:
    policy = replay_config.UnmatchedConversionOutPolicy
    config = replay_config.ReplayConfig(
        portfolio_currency="EUR",
        reward_basis=replay_config.RewardBasis.ZERO,
        conversion_dest_basis=replay_config.ConversionDestBasis.CARRY_COST,
        unmatched_transfer_in=replay_config.UnmatchedTransferInPolicy.ZERO,
        fee_handling=replay_config.FeeHandling.TX_CURRENCY,
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
    return TaxSummary2086(year, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)


@dataclass
class _Operations2086:
    """Achats et ventes jusqu'à la fin de l'année, dans l'ordre du rejeu ; les conversions sont en sursis."""

    year_end: datetime
    steps: list[replay_config.ReplayEvent] = field(default_factory=list)

    def on_event(self, ev: replay_config.ReplayEvent) -> None:
        if ev.kind in ("BUY", "SELL") and ev.tx_dt is not None and ev.tx_dt <= self.year_end:
            self.steps.append(ev)

    def cession_days(self) -> set[date]:
        return {cast(datetime, ev.tx_dt).date() for ev in self.steps if ev.kind == "SELL"}


def _event(ev: replay_config.ReplayEvent, tx_dt: datetime, lines: CessionLines) -> TaxEvent2086:
    tx = cast(Transaction, ev.tx)
    long_term = ev.oldest_acquired_at and (tx_dt - ev.oldest_acquired_at).days >= _LONG_TERM_DAYS
    return TaxEvent2086(
        date=cast(datetime, tx.executed_at),
        symbol=ev.symbol,
        event_type=tx.transaction_type.value,
        quantity=float(ev.quantity),
        unit_price=float(ev.price),
        cession_price=float(lines.net_price),
        portfolio_value=float(lines.portfolio_value),
        total_acquisition_cost=float(lines.net_acquisition_cost),
        acquisition_fraction=float(lines.fraction),
        gain_loss=float(lines.gain),
        holding_period="long_terme" if long_term else "court_terme",
        fees=float(ev.fee),
        gross_cession_price=float(lines.gross_price),
        acquisition_cost_gross=float(lines.acquisition_cost_gross),
        prior_fractions=float(lines.prior_fractions),
    )


def _settle(
    ops: _Operations2086, holdings: dict[uuid.UUID, Holdings], prices: PriceCache, year_start: datetime
) -> list[TaxEvent2086]:
    ledger = PortfolioLedger()
    events: list[TaxEvent2086] = []
    for ev in ops.steps:
        if ev.kind == "BUY":
            ledger.acquire(ev.total_cost)
            continue
        tx_dt = cast(datetime, ev.tx_dt)
        before = holdings.get(cast(Transaction, ev.tx).id, {})
        value = portfolio_value(before, ev.symbol, ev.price, prices.get(tx_dt.date(), {}))
        lines = ledger.cede(ev.quantity * ev.price, ev.fee, value)
        if tx_dt >= year_start:
            events.append(_event(ev, tx_dt, lines))
    return events


def _summarize(year: int, events: list[TaxEvent2086]) -> TaxSummary2086:
    total_cessions = sum(e.cession_price for e in events)
    total_pv = sum(e.gain_loss for e in events if e.gain_loss > 0)
    total_mv = sum(e.gain_loss for e in events if e.gain_loss < 0)
    net_pv = total_pv + total_mv
    exempt = Decimal(str(total_cessions)).quantize(_CENT) <= EXEMPTION_THRESHOLD
    rates = pfu_rates(year)
    taxable = Decimal("0") if exempt else max(Decimal("0"), Decimal(str(net_pv)))
    ir, ps = taxable * rates.ir, taxable * rates.ps
    return TaxSummary2086(
        year=year,
        total_cessions=total_cessions,
        total_acquisitions_fraction=sum(e.acquisition_fraction for e in events),
        total_plus_values=total_pv,
        total_moins_values=total_mv,
        net_plus_value=net_pv,
        nb_cessions=len(events),
        nb_court_terme=sum(1 for e in events if e.holding_period == "court_terme"),
        nb_long_terme=sum(1 for e in events if e.holding_period == "long_terme"),
        pfu_total=float(ir + ps),
        pfu_ir=float(ir),
        pfu_ps=float(ps),
        exempt=exempt and bool(events),
        events=events,
    )


class TaxMixin:
    async def compute_tax_2086(
        self, db: AsyncSession, user_id: str, year: int, *, mode: TaxMode = TAX_MODE
    ) -> TaxSummary2086:
        """Plus-values crypto de `year` selon le 2086 (art. 150 VH bis CGI), méthode du portefeuille.

        Rejoue toutes les transactions crypto depuis l'origine : les achats en euros alimentent le prix total
        d'acquisition, chaque vente (années antérieures comprises) en retire sa fraction de capital initial, et les
        conversions crypto → crypto, stablecoins compris, sont en sursis (sans soulte, ni cession ni effet sur le
        PTA). Exonération si les prix de cession nets de l'année n'excèdent pas 305 €. La durée de détention (FIFO,
        730 jours) est indicative : le régime ne distingue pas court et long terme.
        """
        result = await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))
        portfolio_ids = [p.id for p in result.scalars().all()]
        if not portfolio_ids:
            return _empty_summary(year)
        asset_result = await db.execute(select(Asset).where(Asset.portfolio_id.in_(portfolio_ids)))
        crypto_assets = [a for a in asset_result.scalars().all() if a.asset_type == AssetType.CRYPTO]
        if not crypto_assets:
            return _empty_summary(year)
        asset_map = {a.id: a for a in crypto_assets}
        aid_to_symbol: dict[str, str] = {str(a.id): a.symbol.upper() for a in crypto_assets}
        trans_result = await db.execute(
            select(Transaction).where(Transaction.asset_id.in_(list(asset_map))).order_by(Transaction.executed_at.asc())
        )
        all_transactions = list(trans_result.scalars().all())
        replay_txs = sort_transactions(all_transactions) if mode.canonical_sort else all_transactions

        year_end = datetime(year, 12, 31, 23, 59, 59, tzinfo=UTC)
        ops = _Operations2086(year_end)
        replay(replay_txs, aid_to_symbol, mode.config, on_event=ops.on_event)
        prices = await historical_prices(db, aid_to_symbol.values(), ops.cession_days())
        holdings = holdings_before_sales(replay_txs, asset_map, year_end)
        events = _settle(ops, holdings, prices, datetime(year, 1, 1, tzinfo=UTC))
        return _summarize(year, events)
