import logging

from app.core.config import settings
from app.domains.identity.models import User
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

DEFAULT_FRONTEND_URL = "http://localhost:3000"


def _frontend_url() -> str:
    return settings.CORS_ORIGINS[0] if settings.CORS_ORIGINS else DEFAULT_FRONTEND_URL


async def _send(user: User, subject: str, body: str) -> None:
    try:
        await NotificationService()._send_email(
            to_email=user.email, to_name=user.first_name or "", subject=subject, body=body
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Email « %s » non envoyé : %s", subject, exc)


async def send_registration_attempt_notice(user: User) -> None:
    """Prévient le titulaire d'une adresse qu'une inscription vient d'être tentée avec elle."""
    await _send(
        user,
        "Tentative d'inscription avec votre adresse",
        "Quelqu'un vient de tenter de créer un compte InvestAI avec votre adresse email.<br><br>"
        "Vous possédez déjà un compte : aucune action n'est nécessaire. Si vous avez oublié votre mot "
        "de passe, utilisez « Mot de passe oublié » depuis la page de connexion.",
    )


async def send_password_reset_link(user: User, token: str) -> None:
    """Envoie le lien de réinitialisation, valable une heure."""
    url = f"{_frontend_url()}/reset-password?token={token}"
    await _send(
        user,
        "Réinitialisation de votre mot de passe",
        "Vous avez demandé la réinitialisation de votre mot de passe.<br><br>"
        f'<a href="{url}" style="display:inline-block;padding:12px 24px;background:#6366f1;color:#fff;'
        'border-radius:8px;text-decoration:none;font-weight:bold;">Réinitialiser mon mot de passe</a><br><br>'
        "Ce lien est valable <strong>1 heure</strong>.<br>"
        "Si vous n'avez pas fait cette demande, ignorez cet email.",
    )
