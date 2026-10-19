from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class PriceSeries:
    """Cours de clôture quotidiens en EUR, du plus ancien au plus récent."""

    dates: list[datetime] = field(default_factory=list)
    prices: list[float] = field(default_factory=list)
    volumes: list[float] | None = None

    def tail(self, days: int) -> "PriceSeries":
        """Les ``days`` derniers points."""
        if len(self.prices) <= days:
            return self
        volumes = self.volumes[-days:] if self.volumes is not None else None
        return PriceSeries(self.dates[-days:], self.prices[-days:], volumes)
