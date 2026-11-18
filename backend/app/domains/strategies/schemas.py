import datetime as dt
from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.domains.strategies.models import ActionStatus, StrategyStatus


class StrategyActionCreate(BaseModel):
    action: str = Field(..., min_length=1, max_length=100)
    symbol: str | None = None
    amount: float | None = None
    currency: str = "EUR"
    reason: str | None = None


class StrategyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    actions: list[StrategyActionCreate] = Field(default_factory=list)


class StrategyUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    status: StrategyStatus | None = None
    params: dict[str, Any] | None = None


class StrategyActionResponse(BaseModel):
    id: UUID
    strategy_id: UUID
    action: str
    symbol: str | None = None
    amount: float | None = None
    currency: str
    reason: str | None = None
    status: str
    scheduled_at: datetime | None = None
    executed_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StrategyResponse(BaseModel):
    """``rule_summary`` décrit la règle d'un modèle paramétré ; ``ai_reasoning``, ``market_regime`` et
    ``confidence`` ne sont renseignés que sur les stratégies héritées de l'ancienne génération automatique."""

    id: UUID
    user_id: UUID
    name: str
    description: str | None = None
    source: str
    status: str
    params: dict[str, Any]
    rule_summary: str | None = None
    ai_reasoning: str | None = None
    market_regime: str | None = None
    confidence: float | None = None
    actions: list[StrategyActionResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StrategyActionUpdate(BaseModel):
    """Statut ``EXECUTED`` ou ``SKIPPED`` ; ``amount`` remplace le montant prévu (ou le renseigne s'il manquait)."""

    status: ActionStatus | None = None
    amount: float | None = None


Frequency = Literal["weekly", "biweekly", "monthly", "quarterly"]
Symbol = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_upper=True, min_length=1, max_length=20, pattern=r"^[A-Za-z0-9.^\-]+$"),
]
Money = Annotated[float, Field(gt=0, le=1_000_000_000)]
Percent = Annotated[float, Field(gt=0, le=100)]
Periods = Annotated[int, Field(ge=1, le=120)]
ScheduleStart = Annotated[date, Field(ge=date(2000, 1, 1), le=date(2100, 1, 1))]

_WEIGHT_TOLERANCE = 0.01


def _unique_symbols(symbols: list[str]) -> None:
    if len(set(symbols)) != len(symbols):
        raise ValueError("Chaque actif ne doit apparaître qu'une fois")


def _weights_total_100(weights: list[float]) -> None:
    if abs(sum(weights) - 100) > _WEIGHT_TOLERANCE:
        raise ValueError(f"Les pourcentages doivent totaliser 100 % (actuellement {sum(weights):g} %)")


class _TemplateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssetWeight(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: Symbol
    weight_pct: Percent


class DcaParams(_TemplateParams):
    """Achat périodique : ``amount_per_period`` euros à chaque échéance, répartis selon ``weight_pct``."""

    template: Literal["dca"]
    assets: list[AssetWeight] = Field(..., min_length=1, max_length=10)
    amount_per_period: Money
    frequency: Frequency
    periods: Periods
    start_date: ScheduleStart

    @model_validator(mode="after")
    def _check_assets(self) -> "DcaParams":
        _unique_symbols([a.symbol for a in self.assets])
        _weights_total_100([a.weight_pct for a in self.assets])
        return self


class VcaParams(_TemplateParams):
    """Value averaging : la valeur visée de la ligne augmente de ``target_increment`` euros à chaque échéance ;
    on investit l'écart entre cette cible et la valeur de la ligne ce jour-là, plafonné à ``max_per_period``."""

    template: Literal["vca"]
    symbol: Symbol
    target_increment: Money
    frequency: Frequency
    periods: Periods
    start_date: ScheduleStart
    max_per_period: Money | None = None
    allow_sell: bool = False


class ProfitTier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price: Money
    sell_pct: Percent


class ProfitTakingParams(_TemplateParams):
    """Prise de profits par paliers sur ``quantity`` unités choisies par l'utilisateur : à chaque seuil de prix
    (EUR) qu'il fixe, vendre ``sell_pct`` % de cette quantité."""

    template: Literal["profit_taking"]
    symbol: Symbol
    quantity: Annotated[float, Field(gt=0, le=1_000_000_000_000)]
    tiers: list[ProfitTier] = Field(..., min_length=1, max_length=10)

    @model_validator(mode="after")
    def _check_tiers(self) -> "ProfitTakingParams":
        prices = [t.price for t in self.tiers]
        if len(set(prices)) != len(prices):
            raise ValueError("Deux paliers ne peuvent pas avoir le même prix")
        total = sum(t.sell_pct for t in self.tiers)
        if total > 100 + _WEIGHT_TOLERANCE:
            raise ValueError(f"Les paliers vendent plus de 100 % de la quantité ({total:g} %)")
        self.tiers = sorted(self.tiers, key=lambda t: t.price)
        return self


class RebalanceLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: Symbol
    target_pct: Annotated[float, Field(ge=0, le=100)]
    current_value: Annotated[float, Field(ge=0, le=1_000_000_000_000)]


class RebalanceParams(_TemplateParams):
    """Rééquilibrage vers l'allocation cible choisie, à partir des valeurs actuelles **saisies** par l'utilisateur
    (jamais lues dans ses positions) ; on n'agit que si un écart dépasse ``threshold_pct`` points ou qu'un apport
    ``contribution`` est à répartir. ``frequency`` et ``periods`` fixent le calendrier des revues."""

    template: Literal["rebalance"]
    lines: list[RebalanceLine] = Field(..., min_length=2, max_length=20)
    contribution: Annotated[float, Field(ge=0, le=1_000_000_000)] = 0.0
    threshold_pct: Annotated[float, Field(ge=0, le=50)] = 0.0
    frequency: Frequency
    periods: Periods
    start_date: ScheduleStart

    @model_validator(mode="after")
    def _check_lines(self) -> "RebalanceParams":
        _unique_symbols([line.symbol for line in self.lines])
        _weights_total_100([line.target_pct for line in self.lines])
        if sum(line.current_value for line in self.lines) + self.contribution <= 0:
            raise ValueError("Indiquez au moins une valeur actuelle ou un apport")
        return self


TemplateParams = Annotated[
    DcaParams | VcaParams | ProfitTakingParams | RebalanceParams,
    Field(discriminator="template"),
]


class SimulationRequest(BaseModel):
    """``backtest_start`` : date à partir de laquelle rejouer la règle sur l'historique de prix (optionnelle)."""

    params: TemplateParams
    backtest_start: Annotated[date, Field(ge=date(2010, 1, 1))] | None = None


class TemplateStrategyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    params: TemplateParams


class ScheduleLine(BaseModel):
    """Une échéance ; ``amount`` (EUR) vaut ``None`` quand il ne se calcule qu'à l'échéance (VCA) ou pour une
    revue de rééquilibrage, ``date`` vaut ``None`` pour un palier déclenché par le prix."""

    date: dt.date | None = None
    action: Literal["BUY", "SELL", "REVIEW"]
    symbol: str | None = None
    amount: float | None = None
    quantity: float | None = None
    trigger_price: float | None = None
    target_value: float | None = None
    note: str


class BacktestTrade(BaseModel):
    date: dt.date
    action: Literal["BUY", "SELL"]
    symbol: str
    amount: float
    price: float


class BacktestResult(BaseModel):
    """Résultat de la règle rejouée sur les clôtures enregistrées. ``benchmark_*`` : référence sans la règle
    (conserver la quantité pour les paliers, ne jamais rééquilibrer pour le rééquilibrage), absente sinon."""

    available: bool
    reason: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    events_planned: int = 0
    events_simulated: int = 0
    missing_prices: int = 0
    invested_eur: float | None = None
    withdrawn_eur: float | None = None
    final_value_eur: float | None = None
    pnl_eur: float | None = None
    pnl_pct: float | None = None
    benchmark_label: str | None = None
    benchmark_value_eur: float | None = None
    trades: list[BacktestTrade] = []
    trades_truncated: bool = False
    note: str


class SimulationResponse(BaseModel):
    template: str
    rule_summary: str
    schedule: list[ScheduleLine]
    total_buy_eur: float
    total_sell_eur: float
    has_amounts_at_execution: bool
    backtest: BacktestResult | None = None
    disclaimer: str
