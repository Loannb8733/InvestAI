import re

import bcrypt

from app.core.config import settings

BCRYPT_MAX_BYTES = 72
MIN_LENGTH = 10


def _bcrypt_input(password: str) -> bytes:
    return password.encode("utf-8")[:BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    """Hache un mot de passe avec bcrypt ; seuls les 72 premiers octets comptent."""
    return bcrypt.hashpw(_bcrypt_input(password), bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Vérifie un mot de passe contre son hachage bcrypt."""
    return bcrypt.checkpw(_bcrypt_input(plain_password), hashed_password.encode("utf-8"))


def check_password_strength(password: str) -> str:
    """Règle unique de tous les chemins : 10 caractères, une majuscule, un chiffre."""
    if len(password) < MIN_LENGTH:
        raise ValueError("Le mot de passe doit contenir au moins 10 caractères")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Le mot de passe doit contenir au moins une majuscule")
    if not re.search(r"\d", password):
        raise ValueError("Le mot de passe doit contenir au moins un chiffre")
    return password


TIMING_EQUALIZER_HASH = hash_password("not-a-real-password-timing-equalizer")
