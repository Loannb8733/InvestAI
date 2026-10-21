from app.domains.market_data.fx.cold_start import cold_start_rate
from app.domains.market_data.fx.spot import spot_rates
from app.domains.market_data.prices.quote import PriceQuote
from app.domains.portfolio.classification import STABLECOIN_PEGS


async def peg_quote(symbol: str, currency: str) -> PriceQuote | None:
    """Cours d'un stablecoin déduit de sa monnaie d'ancrage ; None si ``symbol`` n'en est pas un."""
    peg = STABLECOIN_PEGS.get(symbol)
    if peg is None:
        return None
    rate = await spot_rates.get(peg, currency) or cold_start_rate(peg, currency)
    return PriceQuote(price=rate) if rate is not None else None
