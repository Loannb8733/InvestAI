from datetime import datetime
from typing import IO, Any
from zoneinfo import ZoneInfo

from openpyxl.styles import Border, Font, PatternFill, Side
from reportlab.lib import colors
from reportlab.lib.colors import Color
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate

BLUE = colors.HexColor("#1e40af")
DARK_BLUE = colors.HexColor("#1e3a8a")
LIGHT_BG = colors.HexColor("#f8fafc")
BORDER_COLOR = colors.HexColor("#e2e8f0")
GREEN = colors.HexColor("#16a34a")
RED = colors.HexColor("#dc2626")

XL_HEADER_FONT = Font(bold=True, color="FFFFFF")
XL_HEADER_FILL = PatternFill(start_color="1e40af", end_color="1e40af", fill_type="solid")
XL_BORDER = Border(
    left=Side(style="thin", color="e2e8f0"),
    right=Side(style="thin", color="e2e8f0"),
    top=Side(style="thin", color="e2e8f0"),
    bottom=Side(style="thin", color="e2e8f0"),
)
XL_MONEY = "#,##0.00 €"
XL_PERCENT = "0.00%"

_PARIS_TZ = ZoneInfo("Europe/Paris")


def money(v: float) -> str:
    return f"{v:,.2f} €"


def fmt_qty(v: float) -> str:
    """Abrège les quantités pour tenir dans les colonnes PDF : M au-delà du million, moins de décimales en grand."""
    abs_v = abs(v)
    if abs_v >= 1_000_000:
        return f"{v / 1_000_000:,.2f}M"
    if abs_v >= 10_000:
        return f"{v:,.0f}"
    if abs_v >= 1:
        return f"{v:,.4f}"
    return f"{v:,.6f}"


def pct(v: float) -> str:
    return f"{v:,.2f} %"


def gain_color(v: float) -> Color:
    return GREEN if v >= 0 else RED


def now_paris() -> datetime:
    return datetime.now(tz=_PARIS_TZ)


def format_paris_dt() -> str:
    now = now_paris()
    return now.strftime("%d/%m/%Y à %H:%M") + " (heure de Paris)"


def _page_footer(canvas: Canvas, doc: BaseDocTemplate) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#94a3b8"))
    page_text = f"Page {canvas.getPageNumber()}"
    canvas.drawCentredString(A4[0] / 2, 1.2 * cm, page_text)
    canvas.restoreState()


def build_doc(buffer: IO[bytes], **kwargs: Any) -> BaseDocTemplate:
    """Document A4 dont chaque page porte le pied « Page N » centré."""
    doc = BaseDocTemplate(buffer, pagesize=A4, **kwargs)
    frame = Frame(
        doc.leftMargin,
        doc.bottomMargin,
        doc.width,
        doc.height,
        id="main",
    )
    template = PageTemplate(id="with_footer", frames=[frame], onPage=_page_footer)
    doc.addPageTemplates([template])
    return doc
