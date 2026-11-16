from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]


@dataclass
class ForecastResult:
    """Prévision d'un modèle ou de l'ensemble : dates, prix, intervalle à 95 % et tendance."""

    dates: list[str]
    prices: list[float]
    confidence_low: list[float]
    confidence_high: list[float]
    trend: str
    trend_strength: float
    model_used: str
    models_detail: list[dict[str, Any]] = field(default_factory=list)
    explanations: list[dict[str, Any]] = field(default_factory=list)


Candidate = tuple[str, ForecastResult]
ModelRunner = Callable[[str, list[float], list[datetime], int], ForecastResult]


def rounded(
    dates: list[str],
    prices: list[float],
    low: list[float],
    high: list[float],
    trend: tuple[str, float],
    model_used: str,
    explanations: list[dict[str, Any]] | None = None,
) -> ForecastResult:
    """Résultat aux prix arrondis à 8 décimales et à la force de tendance arrondie à une décimale."""
    return ForecastResult(
        dates=dates,
        prices=[round(p, 8) for p in prices],
        confidence_low=[round(p, 8) for p in low],
        confidence_high=[round(p, 8) for p in high],
        trend=trend[0],
        trend_strength=round(trend[1], 1),
        model_used=model_used,
        explanations=explanations if explanations is not None else [],
    )
