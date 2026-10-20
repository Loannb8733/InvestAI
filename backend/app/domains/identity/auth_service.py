from app.core.errors import DomainError, UnauthorizedError
from app.domains.identity import guards, mfa
from app.domains.identity.models import User
from app.domains.identity.passwords import TIMING_EQUALIZER_HASH, verify_password
from app.domains.identity.repository import UserRepository
from app.domains.identity.schemas import LoginRequest
from app.domains.identity.sessions import authenticate
from app.domains.identity.tokens import TokenPair, decode_token, issue_pair

INVALID_CREDENTIALS = "Email ou mot de passe invalide"
INVALID_MFA_CODE = "Code MFA invalide"


class AuthService:
    """Connexion, rafraîchissement et déconnexion."""

    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def login(self, credentials: LoginRequest, user_agent: str) -> TokenPair:
        """Vérifie le verrouillage, le mot de passe (en temps constant) puis le second facteur."""
        user = await self._users.by_email(credentials.email, lock=True)
        if user is not None:
            await guards.ensure_not_locked(user.id)
        hashed = user.password_hash if user is not None else TIMING_EQUALIZER_HASH
        if not verify_password(credentials.password, hashed) or user is None:
            if user is not None:
                await guards.record_failure(user.id)
            raise UnauthorizedError(INVALID_CREDENTIALS)
        if not user.is_active:
            raise UnauthorizedError("Ce compte est inactif")
        if user.mfa_enabled:
            await self._second_factor(user, credentials.mfa_code)
        await guards.clear_failures(user.id)
        return issue_pair(str(user.id), user_agent, user.token_version, remember_me=credentials.remember_me)

    async def _second_factor(self, user: User, code: str | None) -> None:
        if not code:
            raise DomainError("MFA code required")
        await guards.ensure_totp_unused(user.id, code)
        if mfa.totp_matches(user.mfa_secret, code):
            await guards.mark_totp_used(user.id, code)
            return
        remaining = mfa.consume_backup_code(user.mfa_backup_codes, code)
        if remaining is None:
            raise UnauthorizedError(INVALID_MFA_CODE)
        user.mfa_backup_codes = remaining
        await self._users.save(user)

    async def refresh(self, refresh_token: str | None, user_agent: str) -> TokenPair:
        if not refresh_token:
            raise UnauthorizedError("Aucun token de rafraîchissement fourni")
        user, _ = await authenticate(refresh_token, "refresh", user_agent, self._users)
        return issue_pair(str(user.id), user_agent, user.token_version)

    async def logout(self, tokens: list[tuple[str, int]]) -> None:
        """Révoque chaque jeton fourni, avec son plafond de durée de révocation."""
        for token, cap_s in tokens:
            payload = decode_token(token)
            if payload is not None:
                await guards.revoke(payload, cap_s)
