import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Flowable, Paragraph, Spacer, Table, TableStyle

from app.domains.reports.data import AssetReport, PortfolioSummary
from app.domains.reports.styles import (
    BLUE,
    BORDER_COLOR,
    DARK_BLUE,
    LIGHT_BG,
    build_doc,
    fmt_qty,
    format_paris_dt,
    gain_color,
    money,
    pct,
)

_ASSET_COL_WIDTHS = [2.0, 1.5, 1.6, 2.0, 2.2, 2.0, 1.6, 2.0, 1.5]


def _paragraph_styles() -> tuple[ParagraphStyle, ParagraphStyle, ParagraphStyle]:
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("T", parent=styles["Heading1"], fontSize=24, spaceAfter=30, textColor=BLUE)
    heading_style = ParagraphStyle(
        "H",
        parent=styles["Heading2"],
        fontSize=14,
        spaceBefore=20,
        spaceAfter=10,
        textColor=DARK_BLUE,
    )
    return title_style, heading_style, styles["Normal"]


def _summary_rows(summary: dict[str, Any], pnl: dict[str, Any]) -> list[list[str]]:
    rows = [
        ["Indicateur", "Valeur"],
        ["Valeur totale", money(summary.get("total_value", 0))],
        ["Total investi", money(summary.get("total_invested", 0))],
        ["Plus/Moins-value", money(summary.get("gain_loss", 0))],
        ["Performance", pct(summary.get("gain_loss_percent", 0))],
    ]
    if pnl:
        rows.extend(
            [
                ["", ""],
                ["P&L Latent", money(pnl.get("unrealized_pnl", 0))],
                ["P&L Réalisé", money(pnl.get("realized_pnl", 0))],
                ["Total Frais", money(pnl.get("total_fees", 0))],
                ["P&L Net", money(pnl.get("net_pnl", 0))],
            ]
        )
    return rows


def _summary_section(summary: dict[str, Any], pnl: dict[str, Any], heading_style: ParagraphStyle) -> list[Flowable]:
    t = Table(_summary_rows(summary, pnl), colWidths=[8 * cm, 6 * cm])
    style_cmds: list[tuple[Any, ...]] = [
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 11),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
        ("BACKGROUND", (0, 1), (-1, -1), LIGHT_BG),
        ("GRID", (0, 0), (-1, -1), 1, BORDER_COLOR),
        ("FONTSIZE", (0, 1), (-1, -1), 10),
        ("TOPPADDING", (0, 1), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 8),
    ]
    if pnl:
        style_cmds.append(("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"))
        style_cmds.append(("TEXTCOLOR", (1, -1), (1, -1), gain_color(pnl.get("net_pnl", 0))))
    t.setStyle(TableStyle(style_cmds))
    return [Paragraph("Résumé Global", heading_style), t, Spacer(1, 20)]


def _attribution_section(attr: dict[str, float], heading_style: ParagraphStyle) -> list[Flowable]:
    if not any(v > 0 for v in attr.values()):
        return []
    total_attr = sum(attr.values()) or 1
    labels = [
        ("Alpha (Altcoins)", "alpha"),
        ("Beta (BTC)", "beta"),
        ("Protection (Or)", "protection"),
        ("Munitions (Cash/Stables)", "munitions"),
    ]
    rows = [["Catégorie", "Valeur", "Poids"]]
    for label, key in labels:
        rows.append([label, money(attr.get(key, 0)), pct(attr.get(key, 0) / total_attr * 100)])
    t = Table(rows, colWidths=[6 * cm, 4 * cm, 4 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BLUE),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 1, BORDER_COLOR),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 1), (-1, -1), LIGHT_BG),
            ]
        )
    )
    return [Paragraph("Attribution de Performance", heading_style), t, Spacer(1, 20)]


def _cash_flow_section(cf: dict[str, Any], summary: dict[str, Any], heading_style: ParagraphStyle) -> list[Flowable]:
    if not (cf.get("total_deposits", 0) > 0 or cf.get("total_withdrawals", 0) > 0):
        return []
    gain = summary.get("gain_loss", 0)
    rows = [
        ["Flux", "Montant"],
        ["Total déposé", money(cf.get("total_deposits", 0))],
        ["Total retiré", money(cf.get("total_withdrawals", 0))],
        ["Flux nets (dépôts − retraits)", money(cf.get("net_flows", 0))],  # noqa: RUF001
        ["Plus/Moins-value réelle", money(gain)],
    ]
    t = Table(rows, colWidths=[8 * cm, 6 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BLUE),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 1, BORDER_COLOR),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 1), (-1, -1), LIGHT_BG),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("TEXTCOLOR", (1, -1), (1, -1), gain_color(gain)),
            ]
        )
    )
    return [Paragraph("Flux de Trésorerie", heading_style), t, Spacer(1, 20)]


def _portfolios_section(portfolios: list[PortfolioSummary], heading_style: ParagraphStyle) -> list[Flowable]:
    if not portfolios:
        return []
    rows = [["Nom", "Valeur", "Investi", "+/- Value", "Perf.", "Actifs"]]
    for p in portfolios:
        rows.append(
            [
                p.name,
                money(p.total_value),
                money(p.total_invested),
                money(p.gain_loss),
                pct(p.gain_loss_percent),
                str(p.asset_count),
            ]
        )
    t = Table(rows, colWidths=[4 * cm, 2.8 * cm, 2.8 * cm, 2.5 * cm, 2 * cm, 1.5 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BLUE),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 1, BORDER_COLOR),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
            ]
        )
    )
    return [Paragraph("Portefeuilles", heading_style), t, Spacer(1, 20)]


def _asset_row(a: AssetReport) -> list[str]:
    return [
        a.symbol,
        a.asset_type.upper()[:6],
        fmt_qty(a.quantity),
        money(a.avg_buy_price),
        money(a.current_value),
        money(a.gain_loss),
        pct(a.gain_loss_percent),
        money(a.breakeven_price) if a.breakeven_price else "N/A",
        f"{a.risk_weight:.1f}%" if a.risk_weight else "N/A",
    ]


def _assets_section(assets: list[AssetReport], heading_style: ParagraphStyle) -> list[Flowable]:
    if not assets:
        return []
    rows = [["Symbole", "Type", "Qté", "PRU", "Valeur", "+/- Value", "Perf.", "Break-even", "Risque"]]
    rows.extend(_asset_row(a) for a in assets)
    t = Table(rows, colWidths=[w * cm for w in _ASSET_COL_WIDTHS])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BLUE),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 1, BORDER_COLOR),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
            ]
        )
    )
    return [Paragraph("Détail des Actifs", heading_style), t]


def render_performance_pdf(data: dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    doc = build_doc(
        buffer,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    title_style, heading_style, normal_style = _paragraph_styles()
    summary = data.get("summary", {})
    pnl = data.get("pnl_data", {})
    elements: list[Flowable] = [
        Paragraph("Rapport de Performance", title_style),
        Paragraph(f"Généré le {format_paris_dt()}", normal_style),
        Spacer(1, 20),
    ]
    elements += _summary_section(summary, pnl, heading_style)
    elements += _attribution_section(data.get("attribution", {}), heading_style)
    elements += _cash_flow_section(data.get("cash_flows", {}), summary, heading_style)
    elements += _portfolios_section(data.get("portfolios", []), heading_style)
    elements += _assets_section(data.get("assets", []), heading_style)
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
