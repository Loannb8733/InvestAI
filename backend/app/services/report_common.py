"""Shared report helpers: crypto-class maps, ReportLab/Excel styles, number
formatting, and the page-footer document builder. Imported by report_service
and the report cluster modules (report_tax, and future performance/transactions/
rebalancing splits) so the styling lives in one place."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Dict, Tuple
from zoneinfo import ZoneInfo

from openpyxl.styles import Border, Font, PatternFill, Side
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate

CRYPTO_ASSET_CLASSES: Dict[str, str] = {
    # Layer 1
    "BTC": "L1",
    "ETH": "L1",
    "SOL": "L1",
    "ADA": "L1",
    "AVAX": "L1",
    "DOT": "L1",
    "ATOM": "L1",
    "NEAR": "L1",
    "SUI": "L1",
    "APT": "L1",
    "ALGO": "L1",
    "XTZ": "L1",
    "EGLD": "L1",
    "FTM": "L1",
    "HBAR": "L1",
    "ICP": "L1",
    "TON": "L1",
    "SEI": "L1",
    "KAS": "L1",
    "TIA": "L1",
    "INJ": "L1",
    # Layer 2
    "MATIC": "L2",
    "ARB": "L2",
    "OP": "L2",
    "IMX": "L2",
    "MNT": "L2",
    "STRK": "L2",
    "ZK": "L2",
    "METIS": "L2",
    "POL": "L2",
    # DeFi
    "UNI": "DeFi",
    "AAVE": "DeFi",
    "MKR": "DeFi",
    "LDO": "DeFi",
    "SNX": "DeFi",
    "CRV": "DeFi",
    "COMP": "DeFi",
    "SUSHI": "DeFi",
    "CAKE": "DeFi",
    "PENDLE": "DeFi",
    "RUNE": "DeFi",
    "JUP": "DeFi",
    "RAY": "DeFi",
    "GMX": "DeFi",
    # Stablecoins
    "USDT": "Stable",
    "USDC": "Stable",
    "DAI": "Stable",
    "BUSD": "Stable",
    "FDUSD": "Stable",
    "TUSD": "Stable",
    "PYUSD": "Stable",
    "FRAX": "Stable",
    "LUSD": "Stable",
    "USDG": "Stable",
    "EURC": "Stable",
    "EURT": "Stable",
    # Meme
    "DOGE": "Meme",
    "SHIB": "Meme",
    "PEPE": "Meme",
    "FLOKI": "Meme",
    "WIF": "Meme",
    "BONK": "Meme",
    "MEME": "Meme",
    "TURBO": "Meme",
    "BRETT": "Meme",
}

CRYPTO_CLASS_LABELS: Dict[str, str] = {
    "L1": "Layer 1",
    "L2": "Layer 2",
    "DeFi": "DeFi",
    "Stable": "Stablecoins",
    "Meme": "Meme",
    "Other": "Autres",
}


# ── Styles helpers ──────────────────────────────────────────────────

_BLUE = colors.HexColor("#1e40af")
_DARK_BLUE = colors.HexColor("#1e3a8a")
_LIGHT_BG = colors.HexColor("#f8fafc")
_BORDER_COLOR = colors.HexColor("#e2e8f0")
_GREEN = colors.HexColor("#16a34a")
_RED = colors.HexColor("#dc2626")

_XL_HEADER_FONT = Font(bold=True, color="FFFFFF")
_XL_HEADER_FILL = PatternFill(start_color="1e40af", end_color="1e40af", fill_type="solid")
_XL_BORDER = Border(
    left=Side(style="thin", color="e2e8f0"),
    right=Side(style="thin", color="e2e8f0"),
    top=Side(style="thin", color="e2e8f0"),
    bottom=Side(style="thin", color="e2e8f0"),
)
_XL_MONEY = "#,##0.00 €"
_XL_PERCENT = "0.00%"


def _money(v: float) -> str:
    return f"{v:,.2f} €"


def _fmt_qty(v: float) -> str:
    """Format quantity to fit PDF columns: shorten large numbers, trim decimals."""
    abs_v = abs(v)
    if abs_v >= 1_000_000:
        return f"{v / 1_000_000:,.2f}M"
    if abs_v >= 10_000:
        return f"{v:,.0f}"
    if abs_v >= 1:
        return f"{v:,.4f}"
    return f"{v:,.6f}"


def _pct(v: float) -> str:
    return f"{v:,.2f} %"


def _gain_color(v: float):
    return _GREEN if v >= 0 else _RED


_PARIS_TZ = ZoneInfo("Europe/Paris")
_ZERO = Decimal("0")

# FIFO layer key type
FifoKey = Tuple[str, str]


def _now_paris() -> datetime:
    """Current datetime in Europe/Paris timezone."""
    return datetime.now(tz=_PARIS_TZ)


def _format_paris_dt() -> str:
    """Format current Paris datetime for report headers."""
    now = _now_paris()
    return now.strftime("%d/%m/%Y à %H:%M") + " (heure de Paris)"


def _page_footer(canvas, doc):
    """Draw 'Page X / Y' footer on every page."""
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#94a3b8"))
    page_text = f"Page {canvas.getPageNumber()}"
    canvas.drawCentredString(A4[0] / 2, 1.2 * cm, page_text)
    canvas.restoreState()


def _build_doc_with_footer(buffer, **kwargs) -> BaseDocTemplate:
    """Create a BaseDocTemplate with page numbering footer."""
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
