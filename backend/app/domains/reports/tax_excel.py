import io
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.domains.reports.styles import XL_BORDER, XL_HEADER_FILL, XL_HEADER_FONT, XL_MONEY, now_paris
from app.domains.reports.tax import TaxEvent2086, TaxSummary2086
from app.domains.reports.tax_rates import EXEMPTION_THRESHOLD, percent

_EVENT_HEADERS = [
    "Date (l. 211)",
    "Actif",
    "Quantité",
    "Prix unitaire",
    "Valeur globale du portefeuille (l. 212)",
    "Prix de cession (l. 213/217)",
    "Frais (l. 214)",
    "Prix net de frais (l. 218)",
    "Prix total d'acquisition (l. 220)",
    "Fractions antérieures (l. 221)",
    "Prix total d'acquisition net (l. 223)",
    "Fraction de capital initial",
    "PV/MV",
    "Durée (indicative)",
]
_MONEY_COLS = (4, 5, 6, 7, 8, 9, 10, 11, 12, 13)
_GAIN_COL = 13


def _summary_items(tax: TaxSummary2086) -> list[tuple[str, Any, str | None]]:
    return [
        ("Nombre de cessions", tax.nb_cessions, None),
        ("  dont court terme (< 2 ans)", tax.nb_court_terme, None),
        ("  dont long terme (≥ 2 ans)", tax.nb_long_terme, None),
        ("Total des prix de cession nets de frais (ligne 51)", tax.total_cessions, XL_MONEY),
        ("Fractions de capital initial cédées", tax.total_acquisitions_fraction, XL_MONEY),
        ("Total plus-values", tax.total_plus_values, XL_MONEY),
        ("Total moins-values", tax.total_moins_values, XL_MONEY),
        ("Plus-value nette (ligne 52)", tax.net_plus_value, XL_MONEY),
        (f"Exonération (total ≤ {EXEMPTION_THRESHOLD} €)", "oui" if tax.exempt else "non", None),
        ("Plus-value nette imposable", tax.taxable_plus_value, XL_MONEY),
    ]


def _summary_sheet(ws: Worksheet, tax: TaxSummary2086, year: int) -> None:
    ws.title = f"Résumé {year}"
    ws["A1"] = f"Déclaration Fiscale Crypto — Année {year}"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Généré le {now_paris().strftime('%d/%m/%Y')}"
    ws["A2"].font = Font(italic=True, color="666666")
    ws["A4"] = "Résumé des cessions"
    ws["A4"].font = Font(bold=True, size=12)
    summary_items = _summary_items(tax)
    for i, (label, value, fmt) in enumerate(summary_items, 5):
        ws[f"A{i}"] = label
        ws[f"B{i}"] = value
        if fmt:
            ws[f"B{i}"].number_format = fmt
    row = 5 + len(summary_items) + 1
    rates = tax.rates
    ws[f"A{row}"] = f"Estimation fiscale (PFU {percent(rates.total)}, revenus {tax.year})"
    ws[f"A{row}"].font = Font(bold=True, size=12)
    tax_items = [
        (f"Impôt sur le revenu ({percent(rates.ir)})", tax.pfu_ir),
        (f"Prélèvements sociaux ({percent(rates.ps)})", tax.pfu_ps),
        (f"Total PFU ({percent(rates.total)})", tax.pfu_total),
    ]
    for i, (label, value) in enumerate(tax_items, row + 1):
        ws[f"A{i}"] = label
        ws[f"B{i}"] = value
        ws[f"B{i}"].number_format = XL_MONEY
        if label.startswith("Total"):
            ws[f"A{i}"].font = Font(bold=True)
            ws[f"B{i}"].font = Font(bold=True)
    ws.column_dimensions["A"].width = 48
    ws.column_dimensions["B"].width = 18


def _event_values(e: TaxEvent2086) -> list[Any]:
    return [
        e.date.strftime("%d/%m/%Y"),
        e.symbol,
        e.quantity,
        e.unit_price,
        e.portfolio_value,
        e.gross_cession_price,
        e.fees,
        e.cession_price,
        e.acquisition_cost_gross,
        e.prior_fractions,
        e.total_acquisition_cost,
        e.acquisition_fraction,
        e.gain_loss,
        "≥ 2 ans" if e.holding_period == "long_terme" else "< 2 ans",
    ]


def _events_sheet(wb: Workbook, events: list[TaxEvent2086]) -> None:
    ws = wb.create_sheet("Cessions")
    for col, h in enumerate(_EVENT_HEADERS, 1):
        c = ws.cell(row=1, column=col, value=h)
        c.font = XL_HEADER_FONT
        c.fill = XL_HEADER_FILL
        c.border = XL_BORDER
    for row, e in enumerate(sorted(events, key=lambda x: x.date), 2):
        for col, v in enumerate(_event_values(e), 1):
            c = ws.cell(row=row, column=col, value=v)
            c.border = XL_BORDER
            if col in _MONEY_COLS:
                c.number_format = XL_MONEY
            if col == _GAIN_COL:
                c.font = Font(color="16a34a" if e.gain_loss >= 0 else "dc2626")
    for col in range(1, len(_EVENT_HEADERS) + 1):
        ws.column_dimensions[get_column_letter(col)].width = 16


def render_tax_excel(tax: TaxSummary2086, year: int) -> bytes:
    wb = Workbook()
    _summary_sheet(wb.active, tax, year)
    _events_sheet(wb, tax.events)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()
