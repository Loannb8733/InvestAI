from datetime import datetime
from typing import Any

from app.domains.notifications.report_template import wrap

NO_DATA_2 = '<tr><td colspan="2">Aucune donnee</td></tr>'
NO_DATA_3 = '<tr><td colspan="3">Aucune donnee</td></tr>'


def _sign(value: float) -> str:
    return "+" if value >= 0 else ""


def _trend(value: float) -> str:
    return "positive" if value >= 0 else "negative"


def alert_email(
    alert_name: str, asset_symbol: str, current_price: float, target_price: float, condition: str, currency: str
) -> tuple[str, str]:
    """Objet et page du courriel d'un seuil de prix franchi, à la hausse (``above``) ou à la baisse."""
    condition_text = "atteint" if condition == "above" else "descendu sous"
    alert_class = "alert-success" if condition == "above" else "alert-warning"
    content = f"""
        <h2>Alerte declenchee</h2>
        <div class="alert-box {alert_class}">
            <strong>{alert_name}</strong><br>
            {asset_symbol} a {condition_text} votre seuil de {target_price:.2f} {currency}
        </div>
        <p>Prix actuel: <strong>{current_price:.2f} {currency}</strong></p>
        <p>Seuil configure: <strong>{target_price:.2f} {currency}</strong></p>
        <a href="#" class="button">Voir le portefeuille</a>
        """
    subject = f"[InvestAI] Alerte: {asset_symbol} {condition_text} {target_price:.2f} {currency}"
    return subject, wrap(content, f"Alerte: {asset_symbol}")


def _performer_rows(performers: list[dict[str, Any]], css_class: str, sign: str) -> str:
    return "".join(
        f"""
            <tr>
                <td>{p["symbol"]}</td>
                <td class="{css_class}">{sign}{p["change_pct"]:.1f}%</td>
            </tr>
            """
        for p in performers[:3]
    )


def weekly_email(
    user_name: str,
    total_value: float,
    week_change: float,
    week_change_pct: float,
    top_performers: list[dict[str, Any]],
    worst_performers: list[dict[str, Any]],
    currency: str,
) -> tuple[str, str]:
    """Objet et page du rapport hebdomadaire : valeur, variation de la semaine, trois meilleurs et moins bons actifs."""
    change_class, change_sign = _trend(week_change), _sign(week_change)
    top_rows = _performer_rows(top_performers, "positive", "+")
    worst_rows = _performer_rows(worst_performers, "negative", "")
    content = f"""
        <h2>Bonjour {user_name},</h2>
        <p>Voici votre resume hebdomadaire de performance.</p>

        <div style="text-align: center; margin: 24px 0;">
            <div class="metric">
                <div class="metric-value">{total_value:,.2f} {currency}</div>
                <div class="metric-label">Valeur totale</div>
            </div>
            <div class="metric">
                <div class="metric-value {change_class}">{change_sign}{week_change:,.2f} {currency}</div>
                <div class="metric-label">Cette semaine ({change_sign}{week_change_pct:.1f}%)</div>
            </div>
        </div>

        <h3>Top performers</h3>
        <table>
            <thead><tr><th>Actif</th><th>Performance</th></tr></thead>
            <tbody>{top_rows if top_rows else NO_DATA_2}</tbody>
        </table>

        <h3>Moins bons performers</h3>
        <table>
            <thead><tr><th>Actif</th><th>Performance</th></tr></thead>
            <tbody>{worst_rows if worst_rows else NO_DATA_2}</tbody>
        </table>

        <a href="#" class="button">Voir le dashboard complet</a>
        """
    subject = f"[InvestAI] Rapport hebdomadaire - {change_sign}{week_change_pct:.1f}%"
    return subject, wrap(content, "Rapport Hebdomadaire")


def _allocation_rows(allocation: list[dict[str, Any]], currency: str) -> str:
    return "".join(
        f"""
            <tr>
                <td>{a["symbol"]}</td>
                <td>{a["allocation_pct"]:.1f}%</td>
                <td>{a["value"]:,.2f} {currency}</td>
            </tr>
            """
        for a in allocation[:10]
    )


def monthly_email(
    user_name: str,
    total_value: float,
    month_change: float,
    month_change_pct: float,
    ytd_change_pct: float,
    allocation: list[dict[str, Any]],
    currency: str,
) -> tuple[str, str]:
    """Objet et page du rapport mensuel : valeur, variation du mois et de l'année, dix premiers actifs."""
    change_class, change_sign = _trend(month_change), _sign(month_change)
    ytd_class, ytd_sign = _trend(ytd_change_pct), _sign(ytd_change_pct)
    alloc_rows = _allocation_rows(allocation, currency)
    content = f"""
        <h2>Bonjour {user_name},</h2>
        <p>Voici votre rapport mensuel de performance.</p>

        <div style="text-align: center; margin: 24px 0;">
            <div class="metric">
                <div class="metric-value">{total_value:,.2f} {currency}</div>
                <div class="metric-label">Valeur totale</div>
            </div>
            <div class="metric">
                <div class="metric-value {change_class}">{change_sign}{month_change_pct:.1f}%</div>
                <div class="metric-label">Ce mois</div>
            </div>
            <div class="metric">
                <div class="metric-value {ytd_class}">{ytd_sign}{ytd_change_pct:.1f}%</div>
                <div class="metric-label">Depuis le debut de l'annee</div>
            </div>
        </div>

        <h3>Repartition du portefeuille</h3>
        <table>
            <thead><tr><th>Actif</th><th>Allocation</th><th>Valeur</th></tr></thead>
            <tbody>{alloc_rows if alloc_rows else NO_DATA_3}</tbody>
        </table>

        <a href="#" class="button">Voir le rapport complet</a>
        """
    subject = f"[InvestAI] Rapport mensuel - {change_sign}{month_change_pct:.1f}%"
    return subject, wrap(content, "Rapport Mensuel")


def monthly_pdf_name() -> str:
    return f"rapport_mensuel_{datetime.now().strftime('%Y_%m')}.pdf"


def _alerts_section(alerts_triggered: list[dict[str, Any]]) -> str:
    if not alerts_triggered:
        return ""
    items = "".join(f"<li><strong>{alert['symbol']}</strong>: {alert['message']}</li>" for alert in alerts_triggered)
    return f"<h3>Alertes declenchees</h3><ul>{items}</ul>"


def _predictions_section(predictions: list[dict[str, Any]]) -> str:
    if not predictions:
        return ""
    rows = "".join(
        f"""
                <tr>
                    <td>{pred["symbol"]}</td>
                    <td class="{_trend(pred["predicted_change"])}">{_sign(pred["predicted_change"])}{pred["predicted_change"]:.1f}%</td>
                    <td>{pred["confidence"]:.0f}%</td>
                </tr>
                """  # noqa: E501
        for pred in predictions[:5]
    )
    head = "<thead><tr><th>Actif</th><th>Prediction 7j</th><th>Confiance</th></tr></thead><tbody>"
    return f"<h3>Predictions du jour</h3><table>{head}{rows}</tbody></table>"


def _insights_section(insights: list[str]) -> str:
    if not insights:
        return ""
    return "<h3>Insights</h3><ul>" + "".join(f"<li>{insight}</li>" for insight in insights[:5]) + "</ul>"


def digest_email(
    user_name: str, alerts_triggered: list[dict[str, Any]], predictions: list[dict[str, Any]], insights: list[str]
) -> tuple[str, str]:
    """Objet et page du résumé quotidien : alertes déclenchées, prévisions et conseils, chaque section si non vide."""
    content = f"""
        <h2>Bonjour {user_name},</h2>
        <p>Voici votre resume quotidien.</p>

        {_alerts_section(alerts_triggered)}
        {_predictions_section(predictions)}
        {_insights_section(insights)}

        <a href="#" class="button">Acceder au dashboard</a>
        """
    subject = f"[InvestAI] Resume du {datetime.now().strftime('%d/%m/%Y')}"
    return subject, wrap(content, "Resume Quotidien")
