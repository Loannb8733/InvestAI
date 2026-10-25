import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.crowdfunding.models import CrowdfundingProject
from app.domains.portfolio.models import Asset, Portfolio

MAX_LTV = 80
MIN_MARGIN = 10
MIN_INVESTMENT = 100.0
MAX_ALLOCATION = 0.05
DEFAULT_ALLOCATION = 500.0
STABLECOINS = frozenset({"USDT", "USDC", "DAI", "BUSD", "TUSD", "USDG"})


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


async def _holdings(db: AsyncSession, user_id: uuid.UUID) -> tuple[float, float, list[str]]:
    rows = await db.execute(
        select(Asset, Portfolio).join(Portfolio, Asset.portfolio_id == Portfolio.id).where(Portfolio.user_id == user_id)
    )
    total = 0.0
    crowdfunding = 0.0
    for asset, _ in rows.all():
        value = float(asset.current_price or 0) * float(asset.quantity or 0)
        total += value
        if (asset.asset_type.value if asset.asset_type else "other") == "crowdfunding":
            crowdfunding += value
    projects = await db.execute(
        select(CrowdfundingProject)
        .join(Asset, CrowdfundingProject.asset_id == Asset.id)
        .join(Portfolio, Asset.portfolio_id == Portfolio.id)
        .where(Portfolio.user_id == user_id)
    )
    return total, crowdfunding, [project.platform for project in projects.scalars().all()]


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


async def diversification(db: AsyncSession, user_id: uuid.UUID, data: dict[str, Any]) -> dict[str, Any]:
    """Impact du projet sur la diversification : concentration géographique, par type d'actif et rendement/risque.

    La zone se compare à la plateforme des projets existants, faute de localisation enregistrée.
    """
    total, crowdfunding, platforms = await _holdings(db, user_id)
    geographic = _geographic((data.get("location") or "").lower(), platforms)
    new_amount = data.get("collection_amount", 0) or 0
    asset_type = (crowdfunding + new_amount) / (total + new_amount) if total > 0 else 0.0
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


def suggest_investment(data: dict[str, Any], total_capital: float, cash: float) -> dict[str, Any]:
    """Placement suggéré : 5 % du capital, réduit si le projet est corrélé au portefeuille, borné par la moitié du cash.

    Jamais sous le ticket minimum de 100 € ; une forte corrélation est signalée en point de vigilance.
    """
    allocation = total_capital * MAX_ALLOCATION if total_capital > 0 else DEFAULT_ALLOCATION
    correlation = data.get("correlation_score", 0)
    if correlation > 0.5:
        allocation *= 0.4
    elif correlation > 0.3:
        allocation *= 0.7
    suggested = min(allocation, cash * 0.5) if cash > 0 else allocation
    data["suggested_investment"] = round(max(suggested, MIN_INVESTMENT), 2)
    if data.get("diversification_impact") == "degrade":
        vigilance = data.get("points_vigilance", [])
        vigilance.append(
            f"Corrélation élevée ({correlation:.0%}) avec le portefeuille existant"
            f" — allocation réduite à {allocation:.0f}€"
        )
        data["points_vigilance"] = vigilance
    return data


async def capital_and_cash(db: AsyncSession, user_id: uuid.UUID) -> tuple[float, float]:
    """Capital total de l'utilisateur et part en stablecoins, au current_price enregistré de chaque actif."""
    portfolios = (await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))).scalars().all()
    total_capital = 0.0
    cash = 0.0
    for portfolio in portfolios:
        assets = (await db.execute(select(Asset).where(Asset.portfolio_id == portfolio.id))).scalars().all()
        for asset in assets:
            value = float(asset.current_price or 0) * float(asset.quantity or 0)
            total_capital += value
            if asset.symbol and asset.symbol.upper() in STABLECOINS:
                cash += value
    return total_capital, cash
