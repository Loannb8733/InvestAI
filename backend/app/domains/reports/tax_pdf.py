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
from app.domains.reports.tax_rates import EXEMPTION_THRESHOLD, percent

_EVENT_HEADERS = ["Date", "Actif", "Qté", "Valeur (212)", "Prix (217)", "Frais (214)", "PTA net (223)", "Fraction"]
_EVENT_COL_WIDTHS = [1.7, 1.3, 1.5, 2.0, 1.9, 1.4, 2.0, 1.9, 1.9, 1.3]
_FORMULA_NOTE = (
    "Formule 2086 : PV = prix de cession net de frais (l. 218) − PTA net (l. 223) "  # noqa: RUF001
    "× prix de cession hors frais (l. 217) / valeur globale du portefeuille avant la cession (l. 212). "  # noqa: RUF001
    "Les frais ne réduisent pas le quotient ; chaque cession retire sa fraction du PTA. "
    "Les échanges entre crypto-actifs sans soulte, stablecoins compris, sont en sursis et n'apparaissent pas."
)
_LEGAL_NOTICE = (
    "Ce document est fourni à titre indicatif uniquement et ne constitue pas un conseil fiscal. "
    "Veuillez consulter un professionnel pour votre déclaration officielle. "
    "Les plus-values sur crypto-actifs réalisées en {year} sont soumises au prélèvement forfaitaire unique (PFU) "
    "de {total} ({ir} d'impôt sur le revenu + {ps} de prélèvements sociaux), "
    "ou au barème progressif de l'impôt sur le revenu sur option globale (case 3CN). "
    "Le calcul suit la méthode du prix total d'acquisition et de la valeur globale du portefeuille "
    "de l'article 150 VH bis du CGI. Elles sont exonérées si le total des prix de cession de l'année "
    "n'excède pas {threshold} € ; le formulaire 2086 reste à joindre. Les moins-values ne s'imputent que sur les "
    "plus-values de la même année et ne sont pas reportables. Le portefeuille s'apprécie au niveau du foyer "
    "fiscal : les avoirs des autres membres du foyer doivent être ajoutés à la valeur globale et au prix "
    "d'acquisition. La valeur du portefeuille au moment de chaque cession est estimée à partir des cours "
    "historiques disponibles."
)
_EXEMPT_NOTE = (
    "Aucune imposition : le total des prix de cession n'excède pas {threshold} € (art. 150 VH bis II-B du CGI). "
    "Le formulaire 2086 reste à joindre avec le prix de chaque cession."
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


def _net_label(tax: TaxSummary2086) -> str:
    if tax.exempt:
        return f"Plus-value nette (ligne 52), exonérée : cessions ≤ {EXEMPTION_THRESHOLD} €"
    if tax.net_plus_value == 0:
        return "Plus-value nette (ligne 52)"
    box = "3BN" if tax.net_plus_value < 0 else "3AN"
    return f"Plus-value nette (ligne 52, case {box})"


def _summary_section(tax: TaxSummary2086, st: _Styles) -> list[Flowable]:
    rows = [
        ["Description", "Montant"],
        ["Nombre de cessions", str(tax.nb_cessions)],
        ["  dont court terme (< 2 ans)", str(tax.nb_court_terme)],
        ["  dont long terme (≥ 2 ans)", str(tax.nb_long_terme)],
        ["Total des prix de cession nets de frais (ligne 51)", money(tax.total_cessions)],
        ["Fractions de capital initial cédées", money(tax.total_acquisitions_fraction)],
        ["Total plus-values", money(tax.total_plus_values)],
        ["Total moins-values", money(tax.total_moins_values)],
        [_net_label(tax), money(tax.net_plus_value)],
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
    rates = tax.rates
    rows = [
        ["Composante", "Taux", "Montant"],
        ["Plus-value nette imposable", "", money(tax.taxable_plus_value)],
        ["Impôt sur le revenu", percent(rates.ir), money(tax.pfu_ir)],
        ["Prélèvements sociaux", percent(rates.ps), money(tax.pfu_ps)],
        ["Total PFU", percent(rates.total), money(tax.pfu_total)],
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
        Paragraph(f"2. Estimation de l'imposition (PFU {percent(rates.total)}, revenus {tax.year})", st.heading),
        t,
    ]
    if tax.exempt:
        elements.append(Spacer(1, 5))
        elements.append(Paragraph(_EXEMPT_NOTE.format(threshold=EXEMPTION_THRESHOLD), st.info))
    elif tax.net_plus_value <= 0:
        elements.append(Spacer(1, 5))
        elements.append(Paragraph("Aucune imposition : la plus-value nette est négative ou nulle.", st.info))
    elements.append(Spacer(1, 20))
    return elements


def _event_row(e: TaxEvent2086) -> list[str]:
    return [
        e.date.strftime("%d/%m/%Y"),
        e.symbol,
        f"{e.quantity:,.6f}",
        money(e.portfolio_value),
        money(e.gross_cession_price),
        money(e.fees),
        money(e.total_acquisition_cost),
        money(e.acquisition_fraction),
        money(e.gain_loss),
        "≥2 ans" if e.holding_period == "long_terme" else "<2 ans",
    ]


def _events_table(events: list[TaxEvent2086]) -> Table:
    ordered = sorted(events, key=lambda x: x.date)
    rows = [[*_EVENT_HEADERS, "PV/MV", "Durée"]]
    rows.extend(_event_row(e) for e in ordered)
    t = Table(rows, colWidths=[w * cm for w in _EVENT_COL_WIDTHS])
    style_cmds: list[tuple[Any, ...]] = [
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 1, BORDER_COLOR),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
    ]
    for i, e in enumerate(ordered, 1):
        style_cmds.append(("TEXTCOLOR", (8, i), (8, i), gain_color(e.gain_loss)))
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


def _legal_notice(tax: TaxSummary2086) -> str:
    rates = tax.rates
    return _LEGAL_NOTICE.format(
        year=tax.year,
        total=percent(rates.total),
        ir=percent(rates.ir),
        ps=percent(rates.ps),
        threshold=EXEMPTION_THRESHOLD,
    )


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
    elements.append(Paragraph(_legal_notice(tax), st.info))
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
