from decimal import Decimal
from typing import Any

from app.domains.planning.simulations.schemas import ProjectionParameters, ProjectionResult


def _year_point(
    year: int, value: Decimal, initial_value: Decimal, total_contributions: Decimal, deflator: Decimal | None
) -> dict[str, Any]:
    real_value = value if deflator is None else value / deflator
    return {
        "year": year,
        "nominal_value": float(round(value, 2)),
        "real_value": float(round(real_value, 2)),
        "contributions": float(round(total_contributions, 2)),
        "returns": float(round(value - initial_value - total_contributions, 2)),
    }


def build_projection(current_value: float, params: ProjectionParameters, currency: str) -> ProjectionResult:
    """Capitalisation mensuelle en ``Decimal`` au rendement net du TER, avec un point par année (de 0 à ``years``)
    et une valeur réelle déflatée par l'inflation quand ``inflation_adjustment`` est vrai."""
    projections: list[dict[str, Any]] = []
    value = Decimal(str(current_value))
    initial_value = value
    net_annual_return = Decimal(str(params.expected_return)) - Decimal(str(params.expense_ratio))
    monthly_return = net_annual_return / 100 / 12
    monthly_contribution = Decimal(str(params.monthly_contribution))
    inflation = Decimal(str(params.inflation_rate)) / 100
    total_contributions = Decimal("0")

    for year in range(params.years + 1):
        deflator = (1 + inflation) ** year if params.inflation_adjustment else None
        projections.append(_year_point(year, value, initial_value, total_contributions, deflator))
        for _ in range(12):
            value = value * (1 + monthly_return) + monthly_contribution
            total_contributions += monthly_contribution

    final_value = projections[-1]["nominal_value"]
    real_final_value = projections[-1]["real_value"]
    total_returns = final_value - current_value - float(total_contributions)

    return ProjectionResult(
        current_value=round(current_value, 2),
        projections=projections,
        final_value=round(final_value, 2),
        total_contributions=float(round(total_contributions, 2)),
        total_returns=round(total_returns, 2),
        real_final_value=round(real_final_value, 2),
        currency=currency,
    )
