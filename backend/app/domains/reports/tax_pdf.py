import io
from typing import Any, NamedTuple

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Flowable, Paragraph, Spacer, Table, TableStyle

from app.domains.reports.styles import (
    BLUE,
    BORDER_COLOR,
    DARK_BLUE,
    LIGHT_BG,
    build_doc,
    gain_color,
    money,
    now_paris,
)
from app.domains.reports.tax import TaxEvent2086, TaxSummary2086

_EVENT_COL_WIDTHS = [2, 1.6, 1.4, 2, 2.4, 2.4, 2.2, 1.6]
_FORMULA_NOTE = (
    "Calcul selon la formule 2086 : PV = Prix cession − "  # noqa: RUF001
    "(Coût acquisition global × Prix cession / Valeur portefeuille)"  # noqa: RUF001
)
_LEGAL_NOTICE = (
    "Ce document est fourni à titre indicatif uniquement et ne constitue pas un conseil fiscal. "
    "Veuillez consulter un professionnel pour votre déclaration officielle. "
    "Les plus-values sur actifs numériques sont soumises au prélèvement forfaitaire unique (PFU) de 30% "
    "(12,8% d'impôt sur le revenu + 17,2% de prélèvements sociaux) "
    "ou au barème progressif de l'impôt sur le revenu sur option. "
    "Le calcul utilise la méthode du Prix Moyen Pondéré (PMP) global du portefeuille "
    "conformément à l'article 150 VH bis du CGI. "
    "La valeur du portefeuille au moment de chaque cession est estimée à partir des données disponibles."
)


class _Styles(NamedTuple):
    title: ParagraphStyle
    heading: ParagraphStyle
    info: ParagraphStyle
    small: ParagraphStyle


def _paragraph_styles() -> _Styles:
    styles = getSampleStyleSheet()
    return _Styles(
        title=ParagraphStyle("T", parent=styles["Heading1"], fontSize=20, spaceAfter=20, textColor=BLUE),
        heading=ParagraphStyle(
            "H",
            parent=styles["Heading2"],
            fontSize=12,
            spaceBefore=15,
            spaceAfter=8,
            textColor=DARK_BLUE,
        ),
        info=ParagraphStyle("I", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#64748b")),
        small=ParagraphStyle("S", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#64748b")),
    )


def _title_section(year: int, st: _Styles) -> list[Flowable]:
    return [
        Paragraph(f"Déclaration Fiscale Crypto — Année {year}", st.title),
        Paragraph("Formulaire 2086 — Plus-values sur actifs numériques", st.heading),
        Paragraph(
            f"Document généré le {now_paris().strftime('%d/%m/%Y')} — À usage indicatif uniquement",
            st.info,
        ),
        Spacer(1, 20),
    ]


def _summary_section(tax: TaxSummary2086, st: _Styles) -> list[Flowable]:
    rows = [
        ["Description", "Montant"],
        ["Nombre de cessions", str(tax.nb_cessions)],
        ["  dont court terme (< 2 ans)", str(tax.nb_court_terme)],
        ["  dont long terme (≥ 2 ans)", str(tax.nb_long_terme)],
        ["Prix total de cession", money(tax.total_cessions)],
        ["Fraction d'acquisition (PMP)", money(tax.total_acquisitions_fraction)],
        ["Total plus-values", money(tax.total_plus_values)],
        ["Total moins-values", money(tax.total_moins_values)],
        ["Plus-value nette imposable", money(tax.net_plus_value)],
    ]
    t = Table(rows, colWidths=[10 * cm, 5 * cm])
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
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("TEXTCOLOR", (1, -1), (1, -1), gain_color(tax.net_plus_value)),
            ]
        )
    )
    return [Paragraph("1. Résumé des cessions", st.heading), t, Spacer(1, 20)]


def _estimate_section(tax: TaxSummary2086, st: _Styles) -> list[Flowable]:
    rows = [
        ["Composante", "Taux", "Montant"],
        ["Plus-value nette imposable", "", money(max(0, tax.net_plus_value))],
        ["Impôt sur le revenu", "12,8%", money(tax.ir_12_8)],
        ["Prélèvements sociaux", "17,2%", money(tax.ps_17_2)],
        ["Total PFU (Flat Tax)", "30,0%", money(tax.flat_tax_30)],
    ]
    t = Table(rows, colWidths=[8 * cm, 3 * cm, 4 * cm])
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
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fef3c7")),
            ]
        )
    )
    elements: list[Flowable] = [
        Paragraph("2. Estimation de l'imposition (PFU — Flat Tax 30%)", st.heading),
        t,
    ]
    if tax.net_plus_value <= 0:
        elements.append(Spacer(1, 5))
        elements.append(Paragraph("Aucune imposition : la plus-value nette est négative ou nulle.", st.info))
    elements.append(Spacer(1, 20))
    return elements


def _event_row(e: TaxEvent2086) -> list[str]:
    return [
        e.date.strftime("%d/%m/%Y"),
        e.symbol,
        "Conv." if e.event_type == "conversion_out" else "Vente",
        f"{e.quantity:,.6f}",
        money(e.cession_price),
        money(e.acquisition_fraction),
        money(e.gain_loss),
        "≥2 ans" if e.holding_period == "long_terme" else "<2 ans",
    ]


def _events_table(events: list[TaxEvent2086]) -> Table:
    ordered = sorted(events, key=lambda x: x.date)
    rows = [["Date", "Actif", "Type", "Qté", "Prix cession", "Fraction acq.", "PV/MV", "Durée"]]
    rows.extend(_event_row(e) for e in ordered)
    t = Table(rows, colWidths=[w * cm for w in _EVENT_COL_WIDTHS])
    style_cmds: list[tuple[Any, ...]] = [
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 1, BORDER_COLOR),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
    ]
    for i, e in enumerate(ordered, 1):
        style_cmds.append(("TEXTCOLOR", (6, i), (6, i), gain_color(e.gain_loss)))
    t.setStyle(TableStyle(style_cmds))
    return t


def _events_section(tax: TaxSummary2086, st: _Styles) -> list[Flowable]:
    if not tax.events:
        return [
            Paragraph("Aucune cession d'actifs numériques enregistrée pour cette année.", st.info),
            Spacer(1, 30),
        ]
    return [
        Paragraph("3. Détail des cessions", st.heading),
        Paragraph(_FORMULA_NOTE, st.small),
        Spacer(1, 8),
        _events_table(tax.events),
        Spacer(1, 30),
    ]


def render_tax_pdf(tax: TaxSummary2086, year: int) -> bytes:
    buffer = io.BytesIO()
    doc = build_doc(
        buffer,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    st = _paragraph_styles()
    elements = _title_section(year, st)
    elements += _summary_section(tax, st)
    elements += _estimate_section(tax, st)
    elements += _events_section(tax, st)
    elements.append(Paragraph("Mentions importantes", st.heading))
    elements.append(Paragraph(_LEGAL_NOTICE, st.info))
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
