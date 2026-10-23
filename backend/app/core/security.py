from cryptography.fernet import Fernet, MultiFernet

from app.core.config import settings


def get_fernet() -> MultiFernet | None:
    """Chiffrement Fernet avec rotation : FERNET_KEY chiffre, FERNET_OLD_KEYS (séparées par des virgules) déchiffrent encore."""
    if not settings.FERNET_KEY:
        return None
    old_keys = [k.strip() for k in (settings.FERNET_OLD_KEYS or "").split(",") if k.strip()]
    return MultiFernet([Fernet(settings.FERNET_KEY.encode()), *(Fernet(k.encode()) for k in old_keys)])


def encrypt_api_key(api_key: str) -> str:
    """Chiffre un secret (clé d'API, secret TOTP) ; lève ValueError sans FERNET_KEY."""
    fernet = get_fernet()
    if fernet is None:
        raise ValueError("FERNET_KEY not configured")
    encrypted: str = fernet.encrypt(api_key.encode()).decode()
    return encrypted


def decrypt_api_key(encrypted_key: str) -> str:
    """Déchiffre un secret chiffré par :func:`encrypt_api_key` ; lève ValueError sans FERNET_KEY."""
    fernet = get_fernet()
    if fernet is None:
        raise ValueError("FERNET_KEY not configured")
    decrypted: str = fernet.decrypt(encrypted_key.encode()).decode()
    return decrypted
