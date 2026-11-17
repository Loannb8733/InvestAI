from pydantic import BaseModel


class PortfolioPosition(BaseModel):
    """Une position de quantité positive ; les champs de projet n'existent que pour un bien valorisé à son coût."""

    id: str
    symbol: str
    name: str | None
    asset_type: str
    exchange: str | None
    quantity: float
    avg_buy_price: float
    total_invested: float
    current_price: float | None
    current_value: float
    gain_loss: float
    gain_loss_percent: float
    change_percent_24h: float
    total_fees: float
    breakeven_price: float
    first_buy_date: str | None
    holding_days: int | None
    annualized_return: float | None
    dividend_income: float
    fx_gain: float
    asset_gain: float
    total_return: float
    risk_weight: float
    interest_rate: float | None = None
    maturity_date: str | None = None
    project_status: str | None = None
    invested_amount: float | None = None


class StablecoinHolding(BaseModel):
    """Un stablecoin valorisé à son cours, avec l'écart à sa parité."""

    id: str
    symbol: str
    quantity: float
    value: float
    unit_price: float
    depeg_warning: bool
    depeg_percent: float | int


class FiatHolding(BaseModel):
    """Une monnaie détenue, valorisée au taux de change."""

    id: str
    symbol: str
    quantity: float
    value: float


class ProjectSummary(BaseModel):
    """Synthèse des biens valorisés à leur montant investi."""

    total_invested: float
    active_projects: int
    completed_projects: int
    projected_annual_interest: float
    next_maturity: str | None


class ExchangeSales(BaseModel):
    """Gain réalisé et coût sorti des ventes d'une plateforme."""

    realized: float
    cost_sold: float


class PortfolioPerformance(BaseModel):
    """Positions, liquidités et gain total d'un portefeuille ; un portefeuille vide n'a pas les champs facultatifs."""

    total_value: float
    total_invested: float
    unrealized_gain: float
    total_dividend_income: float
    assets_count: int
    assets: list[PortfolioPosition]
    cash_from_stablecoins: float
    stablecoins: list[StablecoinHolding]
    cash_from_fiat: float
    fiat_assets: list[FiatHolding]
    available_liquidity: float = 0.0
    forex_stale: bool = False
    unpriced_symbols: list[str] = []
    crowdfunding_summary: ProjectSummary | None = None
    total_gain_loss: float
    total_gain_loss_percent: float
    total_return: float
    by_exchange: dict[str, ExchangeSales]


class SoldAsset(BaseModel):
    """Un actif soldé ou presque, avec ses montants achetés et vendus."""

    id: str
    symbol: str
    name: str | None
    asset_type: str
    exchange: str | None
    current_quantity: float
    total_bought: float
    total_bought_value: float
    total_sold: float
    total_sold_value: float
    total_fees: float
    realized_gain: float
    first_transaction: str | None
    last_transaction: str | None


class PortfolioHistory(BaseModel):
    """Historique d'investissement d'un portefeuille ; un portefeuille vide n'a pas `total_sold_fiat`."""

    total_invested_all_time: float
    total_sold: float
    total_sold_fiat: float = 0.0
    total_fees: float
    realized_gains: float
    current_holdings_count: int
    sold_assets_count: int
    sold_assets: list[SoldAsset]
    by_exchange: dict[str, ExchangeSales]
    realized_by_year: dict[str, float]
