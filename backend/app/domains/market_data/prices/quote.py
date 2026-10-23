from dataclasses import dataclass, replace
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PriceQuote:
    """Cours courant d'un actif, exprimé dans la devise demandée."""

    price: Decimal
    change_percent_24h: float = 0.0
    change_24h: float = 0.0
    volume_24h: float = 0.0
    market_cap: float = 0.0

    def converted(self, rate: Decimal) -> "PriceQuote":
        """Le même cours dans une autre devise ; la variation en pourcentage ne change pas."""
        factor = float(rate)
        return replace(
            self, price=self.price * rate, change_24h=self.change_24h * factor, market_cap=self.market_cap * factor
        )
