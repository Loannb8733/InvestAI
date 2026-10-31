import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.insights import market_regime

logger = logging.getLogger(__name__)

ANNUAL_RETURN = {
    ("conservative", "stress"): 0.02,
    ("conservative", "normal"): 0.05,
    ("conservative", "low"): 0.07,
    ("moderate", "stress"): 0.04,
    ("moderate", "normal"): 0.08,
    ("moderate", "low"): 0.12,
    ("aggressive", "stress"): 0.06,
    ("aggressive", "normal"): 0.12,
    ("aggressive", "low"): 0.20,
}

ANNUAL_VOL = {
    ("conservative", "stress"): 0.10,
    ("conservative", "normal"): 0.08,
    ("conservative", "low"): 0.06,
    ("moderate", "stress"): 0.25,
    ("moderate", "normal"): 0.18,
    ("moderate", "low"): 0.14,
    ("aggressive", "stress"): 0.40,
    ("aggressive", "normal"): 0.30,
    ("aggressive", "low"): 0.22,
}

_REGIME_LABELS = {"stress": "Bear", "normal": "Normal", "low": "Bull"}


async def current_vol_regime(db: AsyncSession, user_id: str) -> tuple[str, str]:
    """Régime de volatilité (``stress``, ``normal``, ``low``) et son libellé (``Bear``, ``Normal``, ``Bull``) ;
    ``normal`` si la détection échoue."""
    try:
        vol_regime = await market_regime.current_vol_regime()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Vol-regime lookup failed, defaulting to 'normal': %s", exc)
        return "normal", "Normal"
    return vol_regime, _REGIME_LABELS.get(vol_regime, "Normal")
