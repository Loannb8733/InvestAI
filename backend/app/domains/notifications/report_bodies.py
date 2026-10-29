from datetime import datetime
from html import escape
from typing import Any

from app.domains.notifications.formatting import amount, percent
from app.domains.notifications.template import wrap

NO_DATA_2 = '<tr><td colspan="2">Aucune donnée</td></tr>'
NO_DATA_3 = '<tr><td colspan="3">Aucune donnée</td></tr>'


def _trend(value: float) -> str:
    return "positive" if value >= 0 else "negative"


def _performer_rows(performers: list[dict[str, Any]]) -> str:
    return "".join(
        f"""
            <tr>
                <td>{escape(p["symbol"])}</td>
                <td class="{_trend(p["change_pct"])}">{percent(p["change_pct"], signed=True)}</td>
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
    top_rows = _performer_rows(top_performers)
    worst_rows = _performer_rows(worst_performers)
    content = f"""
        <h2>Bonjour {escape(user_name)},</h2>
        <p>Voici votre résumé hebdomadaire de performance.</p>

        <div style="text-align: center; margin: 24px 0;">
            <div class="metric">
                <div class="metric-value">{amount(total_value, currency)}</div>
                <div class="metric-label">Valeur totale</div>
            </div>
            <div class="metric">
                <div class="metric-value {_trend(week_change)}">{amount(week_change, currency, signed=True)}</div>
                <div class="metric-label">Cette semaine ({percent(week_change_pct, signed=True)})</div>
            </div>
        </div>

        <h3>Meilleurs actifs</h3>
        <table>
            <thead><tr><th>Actif</th><th>Performance</th></tr></thead>
            <tbody>{top_rows if top_rows else NO_DATA_2}</tbody>
        </table>

        <h3>Moins bons actifs</h3>
        <table>
            <thead><tr><th>Actif</th><th>Performance</th></tr></thead>
            <tbody>{worst_rows if worst_rows else NO_DATA_2}</tbody>
        </table>

        <a href="#" class="button">Voir le dashboard complet</a>
        """
    subject = f"Rapport hebdomadaire - {percent(week_change_pct, signed=True)}"
    return subject, wrap(content, "Rapport hebdomadaire")


def _allocation_rows(allocation: list[dict[str, Any]], currency: str) -> str:
    return "".join(
        f"""
            <tr>
                <td>{escape(a["symbol"])}</td>
                <td>{percent(a["allocation_pct"])}</td>
                <td>{amount(a["value"], currency)}</td>
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
    alloc_rows = _allocation_rows(allocation, currency)
    content = f"""
        <h2>Bonjour {escape(user_name)},</h2>
        <p>Voici votre rapport mensuel de performance.</p>

        <div style="text-align: center; margin: 24px 0;">
            <div class="metric">
                <div class="metric-value">{amount(total_value, currency)}</div>
                <div class="metric-label">Valeur totale</div>
            </div>
            <div class="metric">
                <div class="metric-value {_trend(month_change)}">{percent(month_change_pct, signed=True)}</div>
                <div class="metric-label">Ce mois</div>
            </div>
            <div class="metric">
                <div class="metric-value {_trend(ytd_change_pct)}">{percent(ytd_change_pct, signed=True)}</div>
                <div class="metric-label">Depuis le début de l'année</div>
            </div>
        </div>

        <h3>Répartition du portefeuille</h3>
        <table>
            <thead><tr><th>Actif</th><th>Allocation</th><th>Valeur</th></tr></thead>
            <tbody>{alloc_rows if alloc_rows else NO_DATA_3}</tbody>
        </table>

        <a href="#" class="button">Voir le rapport complet</a>
        """
    subject = f"Rapport mensuel - {percent(month_change_pct, signed=True)}"
    return subject, wrap(content, "Rapport mensuel")


def monthly_pdf_name() -> str:
    return f"rapport_mensuel_{datetime.now().strftime('%Y_%m')}.pdf"


def digest_email(user_name: str, alerts: list[dict[str, str]]) -> tuple[str, str]:
    """Objet et page du résumé quotidien : chaque alerte déclenchée, son titre puis son message."""
    items = "".join(
        f"<li><strong>{escape(alert['title'])}</strong> : {escape(alert['message'])}</li>" for alert in alerts
    )
    content = f"""
        <h2>Bonjour {escape(user_name)},</h2>
        <p>Voici votre résumé quotidien.</p>

        <h3>Alertes déclenchées</h3>
        <ul>{items}</ul>

        <a href="#" class="button">Accéder au dashboard</a>
        """
    subject = f"Résumé du {datetime.now().strftime('%d/%m/%Y')}"
    return subject, wrap(content, "Résumé quotidien")
