"""Indicateurs d'analyse du tableau de bord : TWR, rendement annualisé, risque, gains."""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.finance_constants import annualized_return_pct
from app.domains.dashboard.schemas import (
    AdvancedMetrics,
    AssetAllocation,
    ConcentrationMetrics,
    MaxDrawdown,
    PnLBreakdown,
    RiskMetrics,
    StressTest,
    ValueAtRisk,
)
from app.domains.dashboard.snapshots.service import snapshot_service

logger = logging.getLogger(__name__)

_MIN_DAYS_FOR_CAGR = 180
_MIN_ELAPSED_DAYS = 30
_MAX_SUBPERIOD_RATIO = 10.0
_RISK_UNAVAILABLE: dict[str, Any] = {
    "volatility": 0.0,
    "sharpe_ratio": 0.0,
    "max_drawdown": {"max_drawdown_percent": 0.0},
    "var_95": {"var_percent": 0.0, "var_amount": 0.0, "confidence_level": 95},
    "concentration": {"hhi": 0.0, "interpretation": "Indisponible", "is_concentrated": False},
}
_STRESS_UNAVAILABLE: dict[str, Any] = {
    "scenario_name": "Indisponible",
    "current_value": 0.0,
    "stressed_value": 0.0,
    "potential_loss": 0.0,
    "potential_loss_percent": 0.0,
}


def compute_period_twr(points: list[dict[str, Any]] | None) -> float | None:
    """Rendement pondéré dans le temps en pourcentage ; une sous-période à valeur nulle est un défaut, écartée."""
    if not points or len(points) < 2:
        return None
    twr = 1.0
    previous: tuple[float, float] | None = None
    for point in points:
        value = float(point.get("value") or 0)
        net_capital = float(point.get("net_capital") or 0)
        if previous is not None and previous[0] > 0:
            ratio = (value - (net_capital - previous[1])) / previous[0]
            if ratio > 0:
                twr *= min(ratio, _MAX_SUBPERIOD_RATIO)
        previous = (value, net_capital)
    return round((twr - 1.0) * 100, 2)


def annualized_roi(metrics: dict[str, Any], first_transaction: datetime | None, days: int) -> float | None:
    """Rendement annualisé depuis le début, ventes comprises ; rien avant six mois d'historique."""
    invested = metrics["total_invested"]
    net_capital = metrics.get("net_capital", invested)
    total_return = metrics["total_value"] + max(0, invested - net_capital)
    if invested <= 0 or total_return <= 0:
        return None
    if first_transaction:
        elapsed = max((datetime.now(UTC) - first_transaction).days, _MIN_ELAPSED_DAYS)
    else:
        elapsed = max(days, _MIN_ELAPSED_DAYS)
    if elapsed < _MIN_DAYS_FOR_CAGR:
        return None
    return annualized_return_pct(float(invested), float(total_return), elapsed / 365.0, floor=-95.0, ceil=1000.0)


async def _risk_figures(
    db: AsyncSession,
    user_id: str,
    metrics: dict[str, Any],
    allocation: list[AssetAllocation],
    days: int,
    history: list[dict[str, Any]],
    roi: float | None,
) -> dict[str, Any]:
    try:
        return await snapshot_service.get_all_risk_metrics(
            db,
            user_id,
            metrics["total_value"],
            [{"symbol": asset.symbol, "value": asset.value} for asset in allocation],
            days,
            history=history,
            roi_annualized=roi,
        )
    except Exception:
        logger.exception("Métriques de risque indisponibles (user=%s, days=%s)", user_id, days)
        return dict(_RISK_UNAVAILABLE)


def _risk_metrics(risk: dict[str, Any]) -> RiskMetrics:
    drawdown = risk["max_drawdown"]
    var = risk["var_95"]
    return RiskMetrics(
        volatility=risk["volatility"],
        sharpe_ratio=risk["sharpe_ratio"],
        max_drawdown=MaxDrawdown(
            max_drawdown_percent=drawdown["max_drawdown_percent"],
            peak_date=drawdown.get("peak_date"),
            trough_date=drawdown.get("trough_date"),
            peak_value=drawdown.get("peak_value"),
            trough_value=drawdown.get("trough_value"),
        ),
        var_95=ValueAtRisk(
            var_percent=var["var_percent"], var_amount=var["var_amount"], confidence_level=var["confidence_level"]
        ),
    )


def _pnl_breakdown(metrics: dict[str, Any]) -> PnLBreakdown:
    pnl = metrics.get("pnl_data", {})
    return PnLBreakdown(
        realized_pnl=pnl.get("realized_pnl", 0),
        unrealized_pnl=pnl.get("unrealized_pnl", 0),
        total_pnl=pnl.get("total_pnl", 0),
        total_fees=pnl.get("total_fees", 0),
        net_pnl=pnl.get("net_pnl", 0),
    )


async def build_advanced_metrics(
    db: AsyncSession,
    user_id: str,
    metrics: dict[str, Any],
    allocation: list[AssetAllocation],
    days: int,
    history: list[dict[str, Any]],
    roi: float | None,
) -> AdvancedMetrics:
    """Assemble risque, concentration, scénarios et gains ; une panne du risque laisse des valeurs neutres."""
    risk = await _risk_figures(db, user_id, metrics, allocation, days, history, roi)
    concentration = risk["concentration"]
    return AdvancedMetrics(
        roi_annualized=round(roi, 2) if roi is not None else None,
        risk_metrics=_risk_metrics(risk),
        concentration=ConcentrationMetrics(
            hhi=concentration["hhi"],
            interpretation=concentration["interpretation"],
            is_concentrated=concentration["is_concentrated"],
            top_asset=concentration.get("top_asset"),
            top_concentration=concentration.get("top_concentration"),
        ),
        stress_tests=[
            StressTest(**risk.get("stress_test_20", _STRESS_UNAVAILABLE)),
            StressTest(**risk.get("stress_test_40", _STRESS_UNAVAILABLE)),
        ],
        pnl_breakdown=_pnl_breakdown(metrics),
    )
