"""Alertes Telegram, en information générale.

Les messages décrivent un état (régime, score, concentration, simulation demandée par l'utilisateur) ; ils ne
proposent ni ordre, ni montant, ni achat ou vente.
"""

import logging
from typing import Any

from app.domains.notifications.telegram.client import telegram_service

logger = logging.getLogger(__name__)

NOT_ADVICE = "<i>Information générale, pas un conseil en investissement.</i>"


def _reason_lines(reasons: list[dict[str, Any]]) -> str:
    return "\n".join(f"  • {r['label']}: {r['detail']}" for r in reasons[:3])


def _portfolio_value(value: float) -> str:
    return f"{value:,.0f} €".replace(",", " ")


async def send_cycle_alert(
    chat_id: str,
    user_id: str,
    advice: dict[str, Any],
    regime: str,
    fear_greed: int | None,
) -> None:
    """Alerte Telegram sur un repère de cycle ; un échec d'envoi est journalisé, jamais levé."""
    try:
        fg_str = f" | Fear & Greed: {fear_greed}" if fear_greed is not None else ""
        message = (
            f"🎯 <b>{advice['title']}</b>\n\n"
            f"{advice['description']}\n\n"
            f"📊 Régime: <b>{regime}</b>{fg_str}\n\n"
            f"{NOT_ADVICE}"
        )

        await telegram_service.send_smart_alert(
            message=message,
            chat_id=chat_id,
            user_id=user_id,
            priority="high" if advice.get("priority") == "critical" else "normal",
            symbol="MARKET",
            alert_type="CYCLE_INSIGHT",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Telegram cycle alert failed: %s", exc)


async def send_euphoria_alert(
    chat_id: str,
    user_id: str,
    fear_greed: int,
    portfolio_value: float,
) -> None:
    """Alerte Telegram d'entrée en zone d'euphorie (BTC en régime sommet et Fear & Greed > 80)."""
    try:
        message = (
            "⚠️ <b>Cycle : zone d'euphorie</b>\n\n"
            "Le BTC est en régime Sommet et le Fear & Greed est à "
            f"{fear_greed}/100, des niveaux proches de ceux des sommets passés. "
            "Historiquement, les corrections qui ont suivi ces phases ont été rapides et profondes.\n\n"
            f"💰 Votre portefeuille : <b>{_portfolio_value(portfolio_value)}</b>\n\n"
            f"{NOT_ADVICE}"
        )

        await telegram_service.send_smart_alert(
            message=message,
            chat_id=chat_id,
            user_id=user_id,
            priority="high",
            symbol="BTC",
            alert_type="EUPHORIA_WARNING",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Telegram euphoria alert failed: %s", exc)


async def send_alpha_alert(
    chat_id: str,
    user_id: str,
    symbol: str,
    score: float,
    predicted_pct: float,
    reasons: list[dict[str, Any]],
) -> None:
    """Alerte Telegram d'un score alpha élevé : constat technique, sans ordre ni bouton d'action."""
    try:
        sign = "+" if predicted_pct >= 0 else ""
        message = (
            f"📈 <b>Score alpha élevé : {symbol}</b>\n\n"
            f"Score: <b>{score:.0f}/100</b>\n"
            f"Variation prévue par le modèle à 7 j : <b>{sign}{predicted_pct:.1f}%</b> "
            "(le modèle ne fait pas mieux qu'une prévision « prix constant » sur l'historique testé)\n\n"
            f"📊 Facteurs :\n{_reason_lines(reasons)}\n\n"
            f"{NOT_ADVICE}"
        )

        await telegram_service.send_smart_alert(
            message=message,
            chat_id=chat_id,
            user_id=user_id,
            priority="normal",
            symbol=symbol,
            alert_type="TOP_ALPHA",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Telegram alpha alert failed for %s: %s", symbol, exc)


async def send_concentration_alert(
    chat_id: str,
    user_id: str,
    symbol: str,
    weight_pct: float,
) -> None:
    """Alerte Telegram quand un actif dépasse 60 % du portefeuille."""
    try:
        message = (
            f"⚠️ <b>Concentration : {symbol}</b>\n\n"
            f"Poids dans le portefeuille : <b>{weight_pct:.1f}%</b>\n"
            "Seuil d'alerte : 60%\n\n"
            "Au-delà de ce seuil, la variation de cet actif détermine l'essentiel de celle du portefeuille."
        )

        await telegram_service.send_smart_alert(
            message=message,
            chat_id=chat_id,
            user_id=user_id,
            priority="high",
            symbol=symbol,
            alert_type="CONCENTRATION_RISK",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Telegram concentration alert failed for %s: %s", symbol, exc)


def _correlation_line(btc_corr: float | None) -> str:
    if btc_corr is None:
        return ""
    corr_label = "faible" if abs(btc_corr) < 0.3 else ("modérée" if abs(btc_corr) < 0.6 else "forte")
    return f"🔗 Corrélation BTC : <b>{btc_corr:.2f}</b> ({corr_label})\n"


def _signal_message(result: dict[str, Any]) -> str:
    conc_status = result.get("concentration_status", "SÉCURISÉE")
    conc_icon = "✅" if conc_status == "SÉCURISÉE" else ("⚠️" if conc_status == "VIGILANCE" else "🚨")
    amount = result.get("amount_eur", 0) or 0
    scenario = f"achat hypothétique de {amount:,.2f} €".replace(",", " ") if amount > 0 else "portefeuille actuel"
    reason_lines = _reason_lines(result.get("reasons", []))

    message = (
        f"🧮 <b>Simulation : {result['symbol']}</b> ({scenario})\n\n"
        f"📊 Score alpha : <b>{result['score']:.0f}/100</b> | Configuration : <b>{result.get('tone', 'neutre')}</b>\n"
        f"{_correlation_line(result.get('btc_correlation'))}"
        f"🛡️ Prob. de ruine à 90 j : {result['prob_ruin_before']:.1f}% → {result['prob_ruin_after']:.1f}% "
        f"(<b>{result['risk_impact']}</b>)\n"
        f"{conc_icon} Concentration : <b>{conc_status}</b> ({result.get('post_purchase_weight_pct', 0):.1f}%)\n"
    )
    if reason_lines:
        message += f"\n📊 Facteurs :\n{reason_lines}"
    return f"{message}\n\n{NOT_ADVICE}"


async def send_signal_report(chat_id: str, user_id: str, result: dict[str, Any]) -> None:
    """Rapport Telegram d'une simulation demandée par l'utilisateur."""
    try:
        await telegram_service.send_smart_alert(
            message=_signal_message(result),
            chat_id=chat_id,
            user_id=user_id,
            priority="normal",
            symbol=result["symbol"],
            alert_type="SIGNAL_VALIDATED",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Telegram signal report failed for %s: %s", result.get("symbol"), exc)


def _tone_line(icon: str, label: str, rows: list[dict[str, Any]]) -> str:
    syms = ", ".join(r["symbol"] for r in rows[:3])
    more = f" (+{len(rows) - 3})" if len(rows) > 3 else ""
    return f"{icon} {len(rows)} configuration(s) {label} : {syms}{more}"


async def send_strategy_recap(
    chat_id: str,
    user_id: str,
    summary: dict[str, Any],
    rows: list[dict[str, Any]],
    total_value: float,
) -> None:
    """Récapitulatif Telegram des configurations techniques des actifs détenus."""
    try:
        lines: list[str] = []
        favorable = [r for r in rows if r.get("tone") == "favorable"]
        unfavorable = [r for r in rows if r.get("tone") == "défavorable"]
        if favorable:
            lines.append(_tone_line("🟢", "favorable(s)", favorable))
        if unfavorable:
            lines.append(_tone_line("🔴", "défavorable(s)", unfavorable))
        if summary.get("neutral", 0) > 0:
            lines.append(f"⚪ {summary['neutral']} configuration(s) neutre(s)")

        message = (
            "📅 <b>Lecture technique hebdo</b>\n\n"
            + "\n".join(lines)
            + f"\n\n💰 Portefeuille : <b>{_portfolio_value(total_value)}</b>\n\n{NOT_ADVICE}"
        )

        await telegram_service.send_smart_alert(
            message=message,
            chat_id=chat_id,
            user_id=user_id,
            priority="normal",
            symbol="STRATEGY",
            alert_type="WEEKLY_STRATEGY",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Telegram strategy recap failed: %s", exc)
