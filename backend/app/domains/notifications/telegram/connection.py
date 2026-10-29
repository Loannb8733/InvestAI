from app.core.config import settings
from app.core.errors import BadGatewayError, DomainError
from app.domains.identity.models import User
from app.domains.notifications.schemas import MessageResponse
from app.domains.notifications.telegram.client import telegram_service

BOT_MISSING = "Le bot Telegram n'est pas configuré (TELEGRAM_BOT_TOKEN manquant)."
CHAT_MISSING = "Telegram non configuré pour votre compte. Ajoutez votre chat_id dans votre profil."
SEND_REFUSED = "Échec de l'envoi. Vérifiez votre chat_id Telegram."


async def send_connection_check(user: User) -> MessageResponse:
    """Envoie un message d'essai au chat Telegram de l'utilisateur ; 400 sans bot ou sans chat, 502 si refusé."""
    if not settings.telegram_bot_enabled:
        raise DomainError(BOT_MISSING)
    if not user.telegram_enabled or not user.telegram_chat_id:
        raise DomainError(CHAT_MISSING)
    sent = await telegram_service.send_message(
        f"✅ <b>InvestAI opérationnel.</b>\nConnecté en tant que {user.first_name} {user.last_name}.",
        chat_id=user.telegram_chat_id,
    )
    if not sent:
        raise BadGatewayError(SEND_REFUSED)
    return MessageResponse(message="Telegram test message sent successfully")
