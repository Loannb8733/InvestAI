"""Taux du prélèvement forfaitaire unique (PFU) par année de revenus, et seuil d'exonération des cessions crypto.

Impôt sur le revenu : 12,8 % (art. 200 C CGI). Prélèvements sociaux sur les revenus du patrimoine : 17,2 %, puis
18,6 % à compter de l'imposition des revenus de 2025 (LFSS 2026, loi n° 2025-1403 du 30/12/2025, art. 12 : CSG de
9,2 % à 10,6 %). Le BOFiP BOI-RPPM-PVBMC-30-30 § 10 indique encore 30 % : il n'est pas à jour.
"""

from dataclasses import dataclass
from decimal import Decimal

EXEMPTION_THRESHOLD = Decimal("305")
IR_RATE = Decimal("0.128")
SOCIAL_RATES: tuple[tuple[int, Decimal], ...] = (
    (2025, Decimal("0.186")),
    (0, Decimal("0.172")),
)


def percent(rate: Decimal) -> str:
    """Taux en pourcentage à la française, une décimale : 0.314 donne « 31,4 % »."""
    return f"{rate * 100:.1f}".replace(".", ",") + " %"


@dataclass(frozen=True)
class PfuRates:
    """PFU d'une année de revenus, en fractions : impôt sur le revenu, prélèvements sociaux et total."""

    year: int
    ir: Decimal
    ps: Decimal

    @property
    def total(self) -> Decimal:
        """Taux global du PFU."""
        return self.ir + self.ps

    @property
    def label(self) -> str:
        """Libellé « 31,4 % (12,8 % + 18,6 %) »."""
        return f"{percent(self.total)} ({percent(self.ir)} + {percent(self.ps)})"


def pfu_rates(year: int) -> PfuRates:
    """Taux applicables aux plus-values réalisées en `year`, imposées l'année suivante."""
    ps = next(rate for since, rate in SOCIAL_RATES if year >= since)
    return PfuRates(year=year, ir=IR_RATE, ps=ps)
