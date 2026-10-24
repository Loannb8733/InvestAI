import io
from typing import Any, NamedTuple

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Flowable, Paragraph, Spacer, Table, TableStyle

from app.domains.reports.classes import CRYPTO_CLASS_LABELS
from app.domains.reports.rebalancing import RebalanceOrder, RebalancingReport
from app.domains.reports.styles import (
    BLUE,
    BORDER_COLOR,
    DARK_BLUE,
    GREEN,
    LIGHT_BG,
    RED,
    build_doc,
    format_paris_dt,
    money,
    pct,
)

_HHI_LEGEND = "HHI &lt; 1500 = bien diversifié | 1500-2500 = modéré | &gt; 2500 = concentré"
_DISCLAIMER = (
    "Ce rapport est fourni à titre indicatif. L'estimation fiscale utilise "
    "les couches FIFO actuelles et le PFU à 30%. Consultez un professionnel "
    "avant d'exécuter les ordres suggérés."
)
_KEY_VALUE_STYLE: list[tuple[Any, ...]] = [
    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
    ("FONTSIZE", (0, 0), (-1, -1), 10),
    ("GRID", (0, 0), (-1, -1), 1, BORDER_COLOR),
    ("TOPPADDING", (0, 0), (-1, -1), 6),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
]


class _Styles(NamedTuple):
    title: ParagraphStyle
    heading: ParagraphStyle
    normal: ParagraphStyle
    info: ParagraphStyle


def _paragraph_styles() -> _Styles:
    styles = getSampleStyleSheet()
    return _Styles(
        title=ParagraphStyle("T", parent=styles["Heading1"], fontSize=20, spaceAfter=20, textColor=BLUE),
        heading=ParagraphStyle(
            "H",
            parent=styles["Heading2"],
            fontSize=13,
            spaceBefore=15,
            spaceAfter=8,
            textColor=DARK_BLUE,
        ),
        normal=styles["Normal"],
        info=ParagraphStyle("I", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#64748b")),
    )


def _header_section(report: RebalancingReport, st: _Styles) -> list[Flowable]:
    return [
        Paragraph("Rapport de Rééquilibrage", st.title),
        Paragraph(f"Généré le {format_paris_dt()}", st.normal),
        Spacer(1, 15),
        Paragraph("1. Valeur du portefeuille crypto", st.heading),
        Paragraph(f"Valeur totale : <b>{money(report.total_value)}</b>", st.normal),
        Spacer(1, 15),
    ]


def _allocation_section(categories: list[dict[str, Any]], st: _Styles) -> list[Flowable]:
    rows = [["Catégorie", "Valeur", "Actuel %", "Cible %", "Écart %", "Écart EUR"]]
    for cat in categories:
        rows.append(
            [
                CRYPTO_CLASS_LABELS.get(cat["category"], cat["category"]),
                money(cat["current_value"]),
                pct(cat["current_pct"]),
                pct(cat["target_pct"]),
                pct(cat["drift_pct"]),
                money(cat["drift_eur"]),
            ]
        )
    t = Table(rows, colWidths=[3.5 * cm, 3 * cm, 2 * cm, 2 * cm, 2 * cm, 3 * cm])
    style_cmds: list[tuple[Any, ...]] = [
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
    for i, cat in enumerate(categories, 1):
        style_cmds.append(("TEXTCOLOR", (4, i), (5, i), GREEN if abs(cat["drift_pct"]) < 3 else RED))
    t.setStyle(TableStyle(style_cmds))
    return [Paragraph("2. Allocation Actuelle vs Cible", st.heading), t, Spacer(1, 20)]


def _orders_table(orders: list[RebalanceOrder]) -> Table:
    rows = [["Action", "Catégorie", "Montant", "PV Latente", "Impôt (PFU 30%)"]]
    for o in orders:
        is_sell = o.action == "sell"
        rows.append(
            [
                "VENDRE" if is_sell else "ACHETER",
                CRYPTO_CLASS_LABELS.get(o.category, o.category),
                money(o.amount_eur),
                money(o.estimated_gain) if is_sell else "—",
                money(o.estimated_tax) if is_sell else "—",
            ]
        )
    t = Table(rows, colWidths=[2.5 * cm, 3.5 * cm, 3 * cm, 3 * cm, 3.5 * cm])
    style_cmds: list[tuple[Any, ...]] = [
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 1, BORDER_COLOR),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
    ]
    for i, o in enumerate(orders, 1):
        style_cmds.append(("TEXTCOLOR", (0, i), (0, i), RED if o.action == "sell" else GREEN))
    t.setStyle(TableStyle(style_cmds))
    return t


def _tax_impact_table(report: RebalancingReport) -> Table:
    rows = [
        ["Total ventes", money(report.total_sell_amount)],
        ["Total achats", money(report.total_buy_amount)],
        ["Plus-value latente estimée", money(report.total_estimated_gain)],
        ["Impôt estimé (PFU 30%)", money(report.total_estimated_tax)],
    ]
    t = Table(rows, colWidths=[8 * cm, 5 * cm])
    t.setStyle(
        TableStyle(
            [
                *_KEY_VALUE_STYLE,
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("TEXTCOLOR", (1, -1), (1, -1), RED),
            ]
        )
    )
    return t


def _orders_section(report: RebalancingReport, st: _Styles) -> list[Flowable]:
    if not report.orders:
        return []
    return [
        Paragraph("3. Ordres de Rééquilibrage Suggérés", st.heading),
        _orders_table(report.orders),
        Spacer(1, 15),
        Paragraph("4. Impact Fiscal du Rééquilibrage", st.heading),
        _tax_impact_table(report),
        Spacer(1, 15),
    ]


def _concentration_section(report: RebalancingReport, st: _Styles) -> list[Flowable]:
    rows = [
        ["HHI avant rééquilibrage", f"{report.hhi_before:.0f}"],
        ["HHI après rééquilibrage", f"{report.hhi_after:.0f}"],
    ]
    t = Table(rows, colWidths=[8 * cm, 5 * cm])
    t.setStyle(TableStyle(list(_KEY_VALUE_STYLE)))
    return [
        Paragraph("5. Score de Diversification (HHI)", st.heading),
        t,
        Spacer(1, 10),
        Paragraph(_HHI_LEGEND, st.info),
        Spacer(1, 20),
    ]


def render_rebalancing_pdf(report: RebalancingReport) -> bytes:
    buffer = io.BytesIO()
    doc = build_doc(
        buffer,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    st = _paragraph_styles()
    elements = _header_section(report, st)
    elements += _allocation_section(report.categories, st)
    elements += _orders_section(report, st)
    elements += _concentration_section(report, st)
    elements.append(Paragraph(_DISCLAIMER, st.info))
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
