from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.analytics.core import AnalyticsCore
from app.domains.analytics.scenarios import HISTORICAL_SCENARIOS, CrisisScenario
from app.domains.portfolio.models import Portfolio
from app.services.metrics_service import metrics_service

DEFAULT_SHOCK = -10


def _shock(base_shock: float, risk_weight: float, avg_risk_weight: float, is_bullish: bool) -> float:
    if not is_bullish and avg_risk_weight > 0 and risk_weight > 0:
        multiplier = min(max(risk_weight / avg_risk_weight, 0.3), 2.5)
        shock_pct = base_shock * multiplier
    else:
        shock_pct = base_shock
    return max(min(shock_pct, 300.0), -95.0)


def _recovery_months(base_recovery: int, avg_risk_weight: float, n_assets: int) -> int:
    if base_recovery > 0 and avg_risk_weight > 0:
        risk_factor = 1.0 + (avg_risk_weight - (100 / max(n_assets, 1))) / 100
        risk_factor = min(max(risk_factor, 0.5), 3.0)
        return round(base_recovery * risk_factor)
    return base_recovery


def _run_scenario(
    scenario_def: CrisisScenario, all_assets: list[Any], total_value: float, avg_risk_weight: float
) -> tuple[dict[str, Any], float]:
    stressed_value = 0.0
    per_asset = []
    is_bullish = any(v > 0 for v in scenario_def["shocks"].values())
    for asset in all_assets:
        val = asset.get("current_value", 0)
        risk_weight = asset.get("risk_weight", 0)
        base_shock = scenario_def["shocks"].get(asset.get("asset_type", "crypto"), DEFAULT_SHOCK)
        shock_pct = _shock(base_shock, risk_weight, avg_risk_weight, is_bullish)
        stressed = val * (1 + shock_pct / 100)
        stressed_value += stressed
        per_asset.append(
            {
                "symbol": asset.get("symbol", ""),
                "name": asset.get("name", ""),
                "current_value": round(val, 2),
                "stressed_value": round(stressed, 2),
                "loss": round(stressed - val, 2),
                "shock_pct": round(shock_pct, 1),
                "risk_weight": risk_weight,
            }
        )

    total_loss = stressed_value - total_value
    total_loss_pct = (total_loss / total_value * 100) if total_value > 0 else 0
    scenario = {
        "id": scenario_def["id"],
        "name": scenario_def["name"],
        "description": scenario_def["description"],
        "duration_days": scenario_def["duration_days"],
        "stressed_value": round(stressed_value, 2),
        "total_loss": round(total_loss, 2),
        "total_loss_pct": round(total_loss_pct, 2),
        "estimated_recovery_months": _recovery_months(
            scenario_def["historical_recovery_months"], avg_risk_weight, len(all_assets)
        ),
        "per_asset": sorted(per_asset, key=lambda x: x["loss"]),
    }
    return scenario, total_loss_pct


class AnalyticsStress(AnalyticsCore):
    async def _live_assets(self, db: AsyncSession, user_id: str, portfolio_id: str | None, currency: str) -> list[Any]:
        portfolios = (await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))).scalars().all()
        all_assets: list[Any] = []
        for portfolio in portfolios:
            if portfolio_id and str(portfolio.id) != portfolio_id:
                continue
            pm = await metrics_service.get_portfolio_metrics(db, str(portfolio.id), currency=currency)
            all_assets.extend(pm.get("assets", []))
        return all_assets

    async def stress_test(
        self,
        db: AsyncSession,
        user_id: str,
        portfolio_id: str | None = None,
        currency: str = "EUR",
        scenario_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Krachs historiques appliqués aux valeurs live de metrics_service : un choc baissier est modulé par le
        risk_weight de chaque actif rapporté à la moyenne (facteur 0,3 à 2,5), borné à [-95 %, +300 %]."""
        all_assets = await self._live_assets(db, user_id, portfolio_id, currency)
        total_value = float(sum(Decimal(str(a.get("current_value", 0))) for a in all_assets))
        if total_value <= 0:
            return {"scenarios": [], "total_value": 0, "currency": currency, "max_drawdown": None}

        n_assets = len(all_assets)
        total_risk_weight = sum(a.get("risk_weight", 0) for a in all_assets) or 1.0
        avg_risk_weight = total_risk_weight / n_assets if n_assets > 0 else 1.0

        scenarios_to_run = HISTORICAL_SCENARIOS
        if scenario_ids:
            scenarios_to_run = [s for s in HISTORICAL_SCENARIOS if s["id"] in scenario_ids]

        scenarios = []
        worst_loss_pct = 0.0
        worst: CrisisScenario | None = None
        for scenario_def in scenarios_to_run:
            scenario, total_loss_pct = _run_scenario(scenario_def, all_assets, total_value, avg_risk_weight)
            scenarios.append(scenario)
            if total_loss_pct < worst_loss_pct:
                worst_loss_pct = total_loss_pct
                worst = scenario_def
        scenarios.sort(key=lambda s: s["total_loss"])

        return {
            "total_value": round(total_value, 2),
            "currency": currency,
            "scenarios": scenarios,
            "max_drawdown": (
                {
                    "value": round(abs(worst_loss_pct), 2),
                    "scenario": worst["name"],
                    "estimated_recovery_months": worst["historical_recovery_months"],
                }
                if worst is not None
                else None
            ),
        }
