import logging
from typing import Any

logger = logging.getLogger(__name__)


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
    """Alerte Telegram sur un conseil de cycle actionnable ; un échec d'envoi est journalisé, jamais levé."""
    try:
        from app.services.telegram_service import telegram_service

        fg_str = f" | Fear & Greed: {fear_greed}" if fear_greed is not None else ""
        message = (
            f"🎯 <b>{advice['title']}</b>\n\n"
            f"{advice['description']}\n\n"
            f"📊 Régime: <b>{regime}</b>{fg_str}\n"
            f"Action: <b>{advice['action']}</b>"
        )

        await telegram_service.send_smart_alert(
            message=message,
            chat_id=chat_id,
            user_id=user_id,
            priority="high" if advice.get("action") == "DIVERSIFIER" else "normal",
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
        from app.services.telegram_service import telegram_service

        message = (
            "⚠️ <b>Alerte Cycle : Zone d'Euphorie</b>\n\n"
            "Le marché entre en zone d'Euphorie (BTC en régime Sommet, "
            f"Fear & Greed à {fear_greed}/100).\n\n"
            f"💰 Votre portefeuille : <b>{_portfolio_value(portfolio_value)}</b>\n\n"
            "📌 Envisagez de sécuriser une partie de vos gains :\n"
            "• Prise de profits partielle (20-30%)\n"
            "• Stop-loss protecteurs\n"
            "• Évitez les nouveaux achats"
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
    order_eur: float = 0.0,
) -> None:
    """Alerte Telegram d'un signal alpha fort, avec les boutons de simulation et de planification."""
    try:
        from app.services.telegram_service import telegram_service

        sign = "+" if predicted_pct >= 0 else ""
        message = (
            f"🚀 <b>Signal Alpha : {symbol}</b>\n\n"
            f"Score: <b>{score:.0f}/100</b> — configuration de surperformance.\n"
            f"Potentiel 7j: <b>{sign}{predicted_pct:.1f}%</b>\n"
            f"Ordre suggéré: <b>{order_eur:,.2f} €</b>\n\n"
            f"📊 Raisons:\n{_reason_lines(reasons)}"
        )

        keyboard = telegram_service.build_alpha_keyboard(user_id, symbol, order_eur)

        await telegram_service.send_smart_alert(
            message=message,
            chat_id=chat_id,
            user_id=user_id,
            priority="high",
            symbol=symbol,
            alert_type="TOP_ALPHA",
            reply_markup=keyboard,
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
        from app.services.telegram_service import telegram_service

        message = (
            f"⚠️ <b>Risque de Concentration : {symbol}</b>\n\n"
            f"Poids dans le portefeuille : <b>{weight_pct:.1f}%</b>\n"
            f"Seuil d'alerte : 60%\n\n"
            f"Envisagez de diversifier pour réduire le risque."
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
    validated = result["validated"]
    pct = result["predicted_7d_pct"]
    sign = "+" if pct >= 0 else ""
    conc_status = result.get("concentration_status", "SÉCURISÉE")

    status_icon = "✅" if validated else "⚠️"
    status_text = "Simulation Alpha Terminée" if validated else "Signal Alpha Non Validé"
    verdict = f"Achat validé pour {result['order_eur']:.2f} €" if validated else "Achat non recommandé"
    conc_icon = "✅" if conc_status == "SÉCURISÉE" else ("⚠️" if conc_status == "VIGILANCE" else "🚨")
    reason_lines = _reason_lines(result.get("reasons", []))

    message = (
        f"{status_icon} <b>{status_text} : {result['symbol']}</b>\n\n"
        f"📊 Score : <b>{result['score']:.0f}/100</b> | Potentiel : <b>{sign}{pct:.1f}%</b>\n"
        f"{_correlation_line(result.get('btc_correlation'))}"
        f"🛡️ Risque : Prob. Ruine {result['prob_ruin_before']:.1f}% → {result['prob_ruin_after']:.1f}% "
        f"(<b>{result['risk_impact']}</b>)\n"
        f"{conc_icon} Concentration : <b>{conc_status}</b> ({result.get('post_purchase_weight_pct', 0):.1f}%)\n"
        f"🚀 Verdict : <b>{verdict}</b>\n"
        f"✅ Précision Dashboard : <b>{result['ecart_eur']:.2f} €</b> d'écart\n"
    )
    if reason_lines:
        message += f"\n📊 Raisons:\n{reason_lines}"

    rebal = result.get("rebalance_suggestion")
    if rebal:
        message += f"\n\n💡 Suggestion : {rebal['reason']} (−{rebal['trim_eur']:.2f} € sur {rebal['trim_symbol']})"  # noqa: RUF001
    return message


async def send_signal_report(chat_id: str, user_id: str, result: dict[str, Any]) -> None:
    """Rapport Telegram détaillé d'un signal alpha, validé ou rejeté."""
    try:
        from app.services.telegram_service import telegram_service

        message = _signal_message(result)

        await telegram_service.send_smart_alert(
            message=message,
            chat_id=chat_id,
            user_id=user_id,
            priority="high" if result["validated"] else "normal",
            symbol=result["symbol"],
            alert_type="SIGNAL_VALIDATED",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Telegram signal report failed for %s: %s", result.get("symbol"), exc)


async def send_strategy_recap(
    chat_id: str,
    user_id: str,
    summary: dict[str, Any],
    rows: list[dict[str, Any]],
    total_value: float,
) -> None:
    """Récapitulatif Telegram hebdomadaire des achats, ventes et maintiens suggérés."""
    try:
        from app.services.telegram_service import telegram_service

        buy_rows = [r for r in rows if "ACHAT" in r["action"] or r["action"] == "DCA"]
        sell_rows = [r for r in rows if "VENDRE" in r["action"] or "PROFITS" in r["action"] or "ALLÉGER" in r["action"]]

        lines: list[str] = []
        if buy_rows:
            buy_syms = ", ".join(r["symbol"] for r in buy_rows[:3])
            lines.append(f"🟢 {summary['buys']} Achat(s) suggéré(s) : {buy_syms}")
        if sell_rows:
            sell_syms = ", ".join(r["symbol"] for r in sell_rows[:3])
            lines.append(f"🔴 {summary['sells']} Vente(s) conseillée(s) : {sell_syms}")
        if summary.get("holds", 0) > 0:
            lines.append(f"⚪ {summary['holds']} position(s) à maintenir")

        message = (
            "📅 <b>Stratégie Hebdo</b>\n\n"
            + "\n".join(lines)
            + f"\n\n💰 Portefeuille : <b>{_portfolio_value(total_value)}</b>"
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
