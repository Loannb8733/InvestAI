import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt

from app.core.config import settings

TokenType = Literal["access", "refresh"]
REMEMBER_ME_DAYS = 30


def fingerprint(user_agent: str) -> str:
    """Empreinte du User-Agent liée au jeton.

    Une gêne au rejeu depuis un autre client, pas une protection contre le vol :
    un User-Agent n'est pas secret. La révocation et la durée de vie courte
    restent les vrais contrôles.
    """
    return hashlib.sha256(user_agent.encode()).hexdigest()[:16]


def create_token(
    subject: str,
    kind: TokenType = "access",
    *,
    lifetime: timedelta | None = None,
    user_agent_fingerprint: str | None = None,
    token_version: int = 0,
    remember_me: bool = False,
) -> str:
    """JWT signé portant le sujet, le type, la génération (``tv``), un ``jti``, l'empreinte et le ``rm`` éventuels."""
    default = (
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        if kind == "access"
        else timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    claims: dict[str, Any] = {
        "sub": subject,
        "exp": datetime.now(UTC) + (lifetime or default),
        "tv": token_version,
        "type": kind,
        "jti": uuid.uuid4().hex,
    }
    if user_agent_fingerprint:
        claims["fp"] = user_agent_fingerprint
    if remember_me:
        claims["rm"] = True
    encoded: str = jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded


def decode_token(token: str) -> dict[str, Any] | None:
    """Revendications d'un jeton valide, None s'il est invalide ou expiré."""
    try:
        payload: dict[str, Any] = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    return payload


def is_stale(payload: dict[str, Any], token_version: int) -> bool:
    """Le jeton appartient-il à une génération périmée ? Un jeton sans ``tv`` vaut la génération zéro."""
    return int(payload.get("tv", 0)) != token_version


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    refresh_days: int


def issue_pair(subject: str, user_agent: str, token_version: int, *, remember_me: bool = False) -> TokenPair:
    """Jeton d'accès et jeton de rafraîchissement liés au User-Agent ; 30 jours avec « se souvenir de moi »."""
    days = REMEMBER_ME_DAYS if remember_me else settings.REFRESH_TOKEN_EXPIRE_DAYS
    fp = fingerprint(user_agent)
    return TokenPair(
        access_token=create_token(subject, "access", user_agent_fingerprint=fp, token_version=token_version),
        refresh_token=create_token(
            subject,
            "refresh",
            lifetime=timedelta(days=days),
            user_agent_fingerprint=fp,
            token_version=token_version,
            remember_me=remember_me,
        ),
        refresh_days=days,
    )
