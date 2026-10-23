from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_session
from app.core.rate_limit import RATE_LIMITS, limiter
from app.domains.identity.account_service import AccountService, ResetOutcome, profile_of
from app.domains.identity.auth_service import AuthService
from app.domains.identity.cookies import clear_auth_cookies, set_auth_cookies
from app.domains.identity.dependencies import CurrentUser, access_token_of, bearer
from app.domains.identity.guards import ACCESS_REVOCATION_CAP_S, REFRESH_REVOCATION_CAP_S
from app.domains.identity.repository import UserRepository
from app.domains.identity.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    MfaCodeRequest,
    MfaSetupResponse,
    PasswordChangeRequest,
    ProfileResponse,
    ProfileUpdate,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    TokenResponse,
)
from app.domains.identity.tokens import TokenPair

router = APIRouter()

REGISTERED = "Inscription enregistrée. Vous pouvez vous connecter avec cette adresse."
RESET_REQUESTED = "Si un compte existe avec cette adresse, un email de réinitialisation a été envoyé."


def get_auth_service(session: Annotated[AsyncSession, Depends(get_session)]) -> AuthService:
    return AuthService(UserRepository(session))


def get_account_service(session: Annotated[AsyncSession, Depends(get_session)]) -> AccountService:
    return AccountService(UserRepository(session))


Auth = Annotated[AuthService, Depends(get_auth_service)]
Accounts = Annotated[AccountService, Depends(get_account_service)]


def _user_agent(request: Request) -> str:
    return request.headers.get("user-agent", "")


def _tokens(response: Response, pair: TokenPair) -> TokenResponse:
    set_auth_cookies(response, pair)
    return TokenResponse(access_token=pair.access_token, refresh_token=pair.refresh_token)


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit(RATE_LIMITS["auth_register"])
async def register(request: Request, data: RegisterRequest, accounts: Accounts) -> RegisterResponse:
    await accounts.register(data)
    return RegisterResponse(message=REGISTERED)


@router.post("/login")
@limiter.limit(RATE_LIMITS["auth_login"])
async def login(request: Request, response: Response, data: LoginRequest, auth: Auth) -> TokenResponse:
    return _tokens(response, await auth.login(data, _user_agent(request)))


@router.post("/refresh")
@limiter.limit(RATE_LIMITS["auth_refresh"])
async def refresh(
    request: Request, response: Response, auth: Auth, data: RefreshRequest | None = None
) -> TokenResponse:
    token = data.refresh_token if data and data.refresh_token else request.cookies.get("refresh_token")
    return _tokens(response, await auth.refresh(token, _user_agent(request)))


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    auth: Auth,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> MessageResponse:
    """Révoque le jeton de rafraîchissement et le jeton d'accès présentés, puis efface les cookies."""
    presented = [
        (request.cookies.get("refresh_token"), REFRESH_REVOCATION_CAP_S),
        (access_token_of(request, credentials), ACCESS_REVOCATION_CAP_S),
    ]
    await auth.logout([(token, cap) for token, cap in presented if token])
    clear_auth_cookies(response)
    return MessageResponse(message="Déconnexion réussie")


@router.post("/mfa/setup")
async def setup_mfa(user: CurrentUser, accounts: Accounts) -> MfaSetupResponse:
    return await accounts.start_mfa(user)


@router.post("/mfa/verify")
@limiter.limit("10/minute")
async def verify_mfa(request: Request, data: MfaCodeRequest, user: CurrentUser, accounts: Accounts) -> MessageResponse:
    await accounts.confirm_mfa(user, data.code)
    return MessageResponse(message="MFA activé avec succès")


@router.post("/mfa/disable")
@limiter.limit("5/minute")
async def disable_mfa(request: Request, data: MfaCodeRequest, user: CurrentUser, accounts: Accounts) -> MessageResponse:
    await accounts.disable_mfa(user, data.code)
    return MessageResponse(message="MFA désactivé avec succès")


@router.get("/me")
async def get_profile(user: CurrentUser) -> ProfileResponse:
    return profile_of(user)


@router.patch("/me")
async def update_profile(data: ProfileUpdate, user: CurrentUser, accounts: Accounts) -> ProfileResponse:
    return await accounts.update_profile(user, data)


@router.post("/change-password")
@limiter.limit("5/minute")
async def change_password(
    request: Request, response: Response, data: PasswordChangeRequest, user: CurrentUser, accounts: Accounts
) -> MessageResponse:
    pair = await accounts.change_password(user, data.current_password, data.new_password, _user_agent(request))
    set_auth_cookies(response, pair)
    return MessageResponse(message="Mot de passe modifié avec succès")


@router.post("/forgot-password")
@limiter.limit("5/minute")
async def forgot_password(request: Request, data: ForgotPasswordRequest, accounts: Accounts) -> MessageResponse:
    await accounts.request_password_reset(data.email)
    return MessageResponse(message=RESET_REQUESTED)


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit("5/minute")
async def reset_password(
    request: Request, data: ResetPasswordRequest, accounts: Accounts
) -> MessageResponse | JSONResponse:
    """Un refus rend 400 sans lever d'exception : l'effacement du jeton expiré doit être validé."""
    outcome = await accounts.reset_password(data.token, data.new_password)
    if outcome is not ResetOutcome.DONE:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": outcome.value})
    return MessageResponse(message=outcome.value)
