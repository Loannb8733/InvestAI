import base64
import json
import secrets
from dataclasses import dataclass
from io import BytesIO

import pyotp
import qrcode
from cryptography.fernet import InvalidToken

from app.core.security import encrypt_api_key, get_fernet
from app.domains.identity.passwords import hash_password, verify_password

ISSUER = "InvestAI"
BACKUP_CODES = 10


@dataclass(frozen=True)
class Enrollment:
    secret: str
    qr_code: str
    backup_codes: list[str]
    stored_secret: str
    stored_backup_codes: str


def enroll(email: str) -> Enrollment:
    """Nouveau secret TOTP (chiffré pour le stockage), son QR code et dix codes de secours (hachés pour le stockage)."""
    secret = pyotp.random_base32()
    image = qrcode.make(pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER), box_size=10, border=5)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    codes = [secrets.token_hex(4) for _ in range(BACKUP_CODES)]
    return Enrollment(
        secret=secret,
        qr_code=f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}",
        backup_codes=codes,
        stored_secret=encrypt_api_key(secret),
        stored_backup_codes=json.dumps([hash_password(code) for code in codes]),
    )


def stored_secret(value: str | None) -> str | None:
    """Secret TOTP en clair ; un secret enregistré avant le chiffrement est rendu tel quel."""
    fernet = get_fernet()
    if not value or fernet is None:
        return value
    try:
        return fernet.decrypt(value.encode()).decode()
    except InvalidToken:
        return value


def totp_matches(stored: str | None, code: str) -> bool:
    secret = stored_secret(stored)
    if not secret:
        return False
    return bool(pyotp.TOTP(secret).verify(code))


def consume_backup_code(stored_codes: str | None, code: str) -> str | None:
    """Liste des codes restants après consommation de ``code``, ou None si aucun ne correspond."""
    codes: list[str] = json.loads(stored_codes) if stored_codes else []
    for index, hashed in enumerate(codes):
        if verify_password(code, hashed):
            return json.dumps(codes[:index] + codes[index + 1 :])
    return None
