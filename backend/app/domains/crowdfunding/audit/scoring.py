import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.crowdfunding.dashboard import capital_outstanding
from app.domains.crowdfunding.repository import repayments_by_project, user_projects
from app.domains.dashboard.metrics.service import metrics_service

MAX_LTV = 80
MIN_MARGIN = 10
MIN_INVESTMENT = 100.0
MAX_ALLOCATION = 0.05
DEFAULT_ALLOCATION = 500.0


def _append_threshold_flags(data: dict[str, Any], flags: list[str]) -> None:
    ltv = data.get("ltv")
    if ltv is not None and ltv > MAX_LTV and not any("LTV" in flag for flag in flags):
        flags.append(f"LTV élevé ({ltv:.1f}%) — risque d'endettement excessif")
    margin = data.get("margin_percent")
    if margin is not None and margin < MIN_MARGIN and not any("Marge" in flag or "marge" in flag for flag in flags):
        flags.append(f"Marge faible ({margin:.1f}%) — peu de marge de sécurité")
    pre_sales = data.get("pre_sales_percent")
    if pre_sales is not None and pre_sales == 0 and not any("pré-commercialisation" in flag.lower() for flag in flags):
        flags.append("Pas de pré-commercialisation — risque de sortie")
    guarantees = data.get("guarantees", [])
    first_rank = any(guarantee.get("rank", "").startswith("1") for guarantee in guarantees)
    if guarantees and not first_rank and not any("1er rang" in flag for flag in flags):
        flags.append("Pas d'hypothèque de 1er rang — garantie affaiblie")


def add_red_flags(data: dict[str, Any]) -> dict[str, Any]:
    """Ajoute les alertes de seuil (LTV, marge, pré-commercialisation, rang d'hypothèque) et durcit le verdict.

    Trois alertes ou plus : « NE_PAS_INVESTIR » ; deux : « INVESTIR » devient « VIGILANCE ».
    """
    flags = list(data.get("red_flags", []))
    _append_threshold_flags(data, flags)
    data["red_flags"] = flags
    if len(flags) >= 3:
        data["verdict"] = "NE_PAS_INVESTIR"
    elif len(flags) >= 2 and data.get("verdict") == "INVESTIR":
        data["verdict"] = "VIGILANCE"
    return data


@dataclass
class Exposure:
    """Patrimoine valorisé comme le tableau de bord : marchés, liquidités et capital restant dû du crowdfunding."""

    total: float = 0.0
    cash: float = 0.0
    crowdfunding: float = 0.0
    platforms: list[str] = field(default_factory=list)


async def portfolio_exposure(db: AsyncSession, user_id: uuid.UUID) -> Exposure:
    """Patrimoine de l'utilisateur ; les plateformes de ses projets servent de zones géographiques."""
    metrics = await metrics_service.get_user_dashboard_metrics(db, str(user_id), currency="EUR", days=0)
    cash = float(metrics.get("available_liquidity") or 0.0)
    projects = await user_projects(db, user_id)
    crowdfunding = capital_outstanding(projects, await repayments_by_project(db, [p.id for p in projects]))
    total = float(metrics.get("total_value") or 0.0) + cash + crowdfunding
    return Exposure(total, cash, crowdfunding, [project.platform for project in projects])


def _allocation(exposure: Exposure) -> float:
    return exposure.total * MAX_ALLOCATION if exposure.total > 0 else DEFAULT_ALLOCATION


def _ticket(allocation: float, cash: float) -> float:
    return max(min(allocation, cash * 0.5) if cash > 0 else allocation, MIN_INVESTMENT)


def _geographic(location: str, platforms: list[str]) -> float:
    if not location or not platforms:
        return 0.0
    words = [word for word in location.split() if len(word) > 3]
    same_area = sum(1 for platform in platforms if any(word in platform.lower() for word in words))
    return same_area / len(platforms)


def _impact(correlation: float) -> str:
    if correlation > 0.6:
        return "degrade"
    if correlation > 0.3:
        return "neutre"
    return "ameliore"


def diversification(exposure: Exposure, data: dict[str, Any]) -> dict[str, Any]:
    """Impact du projet sur la diversification : concentration géographique, par type d'actif et rendement/risque.

    La part du crowdfunding ajoute le ticket que l'on suggérerait sans corrélation ; la zone se compare à la
    plateforme des projets existants, faute de localisation enregistrée.
    """
    geographic = _geographic((data.get("location") or "").lower(), exposure.platforms)
    ticket = _ticket(_allocation(exposure), exposure.cash)
    asset_type = (exposure.crowdfunding + ticket) / (exposure.total + ticket) if exposure.total > 0 else 0.0
    tri = data.get("tri") or 0
    risk_score = data.get("risk_score") or 5
    risk_return = min(1.0, (tri / 15.0) * (1 - risk_score / 10.0))
    correlation = min(1.0, max(0.0, round(geographic * 0.3 + asset_type * 0.4 + risk_return * 0.3, 2)))
    return {
        "diversification_impact": _impact(correlation),
        "correlation_score": correlation,
        "portfolio_concentration": {
            "geographic": {
                "score": round(geographic, 2),
                "detail": f"{int(geographic * 100)}% de projets dans la même zone",
            },
            "asset_type": {
                "score": round(asset_type, 2),
                "detail": f"Crowdfunding = {asset_type * 100:.1f}% du portefeuille après investissement",
            },
            "risk_return": {
                "score": round(risk_return, 2),
                "detail": f"TRI {tri}% avec score risque {risk_score}/10",
            },
        },
    }


def suggest_investment(data: dict[str, Any], exposure: Exposure) -> dict[str, Any]:
    """Placement suggéré : 5 % du patrimoine, réduit si le projet est corrélé, borné par la moitié du cash.

    Jamais sous le ticket minimum de 100 € ; une forte corrélation est signalée en point de vigilance.
    """
    allocation = _allocation(exposure)
    correlation = data.get("correlation_score", 0)
    if correlation > 0.5:
        allocation *= 0.4
    elif correlation > 0.3:
        allocation *= 0.7
    data["suggested_investment"] = round(_ticket(allocation, exposure.cash), 2)
    if data.get("diversification_impact") == "degrade":
        vigilance = data.get("points_vigilance", [])
        vigilance.append(
            f"Corrélation élevée ({correlation:.0%}) avec le portefeuille existant"
            f" — allocation réduite à {allocation:.0f}€"
        )
        data["points_vigilance"] = vigilance
    return data
