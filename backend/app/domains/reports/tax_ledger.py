"""Méthode du portefeuille du formulaire 2086 (art. 150 VH bis III CGI, BOI-RPPM-PVBMC-30-20), en Decimal.

Pour chaque cession : fraction = PTA net (l. 223) * prix de cession hors frais (l. 217) / valeur globale du
portefeuille avant la cession (l. 212), et PV = prix net de frais (l. 218) - fraction ; les frais ne réduisent que
le premier terme (§ 50). Le PTA brut (l. 220) cumule les acquisitions en euros ; le PTA net en retranche les
fractions de toutes les cessions antérieures (l. 221, § 100-110), années exonérées et moins-values comprises.
Les soultes (l. 216 et l. 222) ne sont pas saisies par l'application : elles valent zéro.
"""

from dataclasses import dataclass
from decimal import Decimal

ZERO = Decimal("0")


@dataclass(frozen=True)
class CessionLines:
    """Lignes 212 à 223 d'une cession, et sa fraction de capital initial."""

    portfolio_value: Decimal
    gross_price: Decimal
    fees: Decimal
    acquisition_cost_gross: Decimal
    prior_fractions: Decimal
    fraction: Decimal

    @property
    def net_price(self) -> Decimal:
        """Ligne 218 : prix de cession net de frais."""
        return self.gross_price - self.fees

    @property
    def net_acquisition_cost(self) -> Decimal:
        """Ligne 223 : prix total d'acquisition net des fractions antérieures."""
        return self.acquisition_cost_gross - self.prior_fractions

    @property
    def gain(self) -> Decimal:
        """Plus-value (positive) ou moins-value (négative) de la cession."""
        return self.net_price - self.fraction


@dataclass
class PortfolioLedger:
    """Prix total d'acquisition du portefeuille et fractions de capital initial déjà cédées."""

    acquisition_cost: Decimal = ZERO
    fractions: Decimal = ZERO

    def acquire(self, amount: Decimal) -> None:
        """Acquisition à titre onéreux : le montant payé en euros, frais compris, s'ajoute au PTA brut."""
        self.acquisition_cost += amount

    def cede(self, gross_price: Decimal, fees: Decimal, portfolio_value: Decimal) -> CessionLines:
        """Cession imposable ; une valeur de portefeuille inférieure au prix cédé (données incomplètes) est relevée
        à ce prix, pour que la fraction n'excède jamais le PTA net."""
        value = max(portfolio_value, gross_price)
        net_cost = self.acquisition_cost - self.fractions
        fraction = net_cost * gross_price / value if value > ZERO else ZERO
        lines = CessionLines(
            portfolio_value=value,
            gross_price=gross_price,
            fees=fees,
            acquisition_cost_gross=self.acquisition_cost,
            prior_fractions=self.fractions,
            fraction=fraction,
        )
        self.fractions += fraction
        return lines
