import enum
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.errors import DomainError
from app.domains.identity import emails, mfa
from app.domains.identity.models import User
from app.domains.identity.passwords import hash_password, verify_password
from app.domains.identity.repository import UserRepository
from app.domains.identity.schemas import (
    MfaSetupResponse,
    ProfileResponse,
    ProfileUpdate,
    RegisterRequest,
)
from app.domains.identity.tokens import TokenPair, issue_pair

RESET_LIFETIME = timedelta(hours=1)
DECIMAL_PLACES = {"tmi_rate": 3, "monthly_dca_eur": 2}


class ResetOutcome(enum.Enum):
    DONE = "Mot de passe réinitialisé avec succès. Vous pouvez maintenant vous connecter."
    UNKNOWN = "Lien de réinitialisation invalide ou expiré."
    EXPIRED = "Lien de réinitialisation expiré. Veuillez en demander un nouveau."


def profile_of(user: User) -> ProfileResponse:
    return ProfileResponse(
        id=str(user.id),
        email=user.email,
        role=user.role.value,
        first_name=user.first_name,
        last_name=user.last_name,
        preferred_currency=user.preferred_currency,
        mfa_enabled=user.mfa_enabled,
        telegram_chat_id=user.telegram_chat_id,
        telegram_enabled=user.telegram_enabled,
        tmi_rate=float(user.tmi_rate) if user.tmi_rate is not None else None,
        risk_profile=user.risk_profile,
        monthly_dca_eur=float(user.monthly_dca_eur) if user.monthly_dca_eur is not None else None,
        created_at=user.created_at.isoformat(),
    )


def _new_generation(user: User, password: str) -> None:
    user.password_hash = hash_password(password)
    user.token_version += 1


class AccountService:
    """Inscription, mots de passe, profil et second facteur d'un compte."""

    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def register(self, data: RegisterRequest) -> None:
        """Même effet observable que l'adresse soit libre ou prise : le hachage précède la branche."""
        password_hash = hash_password(data.password)
        existing = await self._users.by_email(data.email)
        if existing is not None:
            await emails.send_registration_attempt_notice(existing)
            return
        await self._users.add(
            User(email=data.email, password_hash=password_hash, first_name=data.first_name, last_name=data.last_name)
        )

    async def change_password(self, user: User, current: str, new: str, user_agent: str) -> TokenPair:
        """Change le mot de passe, coupe toutes les sessions et rend des jetons neufs à la session courante."""
        if not verify_password(current, user.password_hash):
            raise DomainError("Mot de passe actuel incorrect")
        _new_generation(user, new)
        await self._users.save(user)
        return issue_pair(str(user.id), user_agent, user.token_version)

    async def request_password_reset(self, email: str) -> None:
        user = await self._users.by_email(email)
        if user is None or not user.is_active:
            return
        token = secrets.token_urlsafe(48)
        user.password_reset_token = token
        user.password_reset_expires = datetime.now(UTC) + RESET_LIFETIME
        await self._users.save(user)
        await emails.send_password_reset_link(user, token)

    async def reset_password(self, token: str, new_password: str) -> ResetOutcome:
        """Un jeton expiré, ou sans date d'expiration, est refusé et effacé."""
        user = await self._users.by_reset_token(token)
        if user is None:
            return ResetOutcome.UNKNOWN
        expires = user.password_reset_expires
        user.password_reset_token = None
        user.password_reset_expires = None
        if expires is None or datetime.now(UTC) > expires:
            await self._users.save(user)
            return ResetOutcome.EXPIRED
        _new_generation(user, new_password)
        await self._users.save(user)
        return ResetOutcome.DONE

    async def update_profile(self, user: User, changes: ProfileUpdate) -> ProfileResponse:
        for field, value in changes.model_dump(exclude_unset=True).items():
            if field in DECIMAL_PLACES and value is not None:
                value = Decimal(str(round(value, DECIMAL_PLACES[field])))
            setattr(user, field, value)
        return profile_of(await self._users.save(user))

    async def start_mfa(self, user: User) -> MfaSetupResponse:
        if user.mfa_enabled:
            raise DomainError("MFA is already enabled")
        enrollment = mfa.enroll(user.email)
        user.mfa_secret = enrollment.stored_secret
        user.mfa_backup_codes = enrollment.stored_backup_codes
        await self._users.save(user)
        return MfaSetupResponse(
            secret=enrollment.secret, qr_code=enrollment.qr_code, backup_codes=enrollment.backup_codes
        )

    async def confirm_mfa(self, user: User, code: str) -> None:
        if not user.mfa_secret:
            raise DomainError("Configuration MFA non initialisée")
        if not mfa.totp_matches(user.mfa_secret, code):
            raise DomainError("Code MFA invalide")
        user.mfa_enabled = True
        await self._users.save(user)

    async def disable_mfa(self, user: User, code: str) -> None:
        if not user.mfa_enabled:
            raise DomainError("MFA non activé")
        if not mfa.totp_matches(user.mfa_secret, code):
            raise DomainError("Code MFA invalide")
        user.mfa_enabled = False
        user.mfa_secret = None
        user.mfa_backup_codes = None
        await self._users.save(user)
