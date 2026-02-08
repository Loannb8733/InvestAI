"""Report generation service for PDF and Excel exports."""

import io
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction, TransactionType
from app.services.price_service import price_service


# ── Data classes ────────────────────────────────────────────────────

@dataclass
class PortfolioSummary:
    name: str
    total_value: float
    total_invested: float
    gain_loss: float
    gain_loss_percent: float
    asset_count: int


@dataclass
class AssetReport:
    symbol: str
    name: str
    asset_type: str
    quantity: float
    avg_buy_price: float
    current_price: float
    total_invested: float
    current_value: float
    gain_loss: float
    gain_loss_percent: float


@dataclass
class TaxTransaction:
    date: datetime
    symbol: str
    transaction_type: str
    quantity: float
    price: float
    total: float
    fee: float
    gain_loss: Optional[float]


@dataclass
class TaxEvent2086:
    """Single taxable event (cession) per formulaire 2086."""
    date: datetime
    symbol: str
    event_type: str              # "sell" / "conversion_out"
    quantity: float
    unit_price: float
    cession_price: float         # qty × price − fees
    portfolio_value: float       # valeur globale du portefeuille au moment de la cession
    total_acquisition_cost: float  # coût total d'acquisition cumulé
    acquisition_fraction: float  # total_acq × (cession / portfolio_value)
    gain_loss: float             # cession_price − acquisition_fraction
    holding_period: str          # "court_terme" / "long_terme"
    fees: float


@dataclass
class TaxSummary2086:
    """Full tax summary for one fiscal year."""
    year: int
    total_cessions: float
    total_acquisitions_fraction: float
    total_plus_values: float
    total_moins_values: float
    net_plus_value: float
    nb_cessions: int
    nb_court_terme: int
    nb_long_terme: int
    flat_tax_30: float       # PFU total
    ir_12_8: float           # Impôt sur le revenu (12.8%)
    ps_17_2: float           # Prélèvements sociaux (17.2%)
    events: List[TaxEvent2086] = field(default_factory=list)


# ── Styles helpers ──────────────────────────────────────────────────

_BLUE = colors.HexColor('#1e40af')
_DARK_BLUE = colors.HexColor('#1e3a8a')
_LIGHT_BG = colors.HexColor('#f8fafc')
_BORDER_COLOR = colors.HexColor('#e2e8f0')
_GREEN = colors.HexColor('#16a34a')
_RED = colors.HexColor('#dc2626')

_XL_HEADER_FONT = Font(bold=True, color="FFFFFF")
_XL_HEADER_FILL = PatternFill(start_color="1e40af", end_color="1e40af", fill_type="solid")
_XL_BORDER = Border(
    left=Side(style='thin', color='e2e8f0'),
    right=Side(style='thin', color='e2e8f0'),
    top=Side(style='thin', color='e2e8f0'),
    bottom=Side(style='thin', color='e2e8f0'),
)
_XL_MONEY = '#,##0.00 €'
_XL_PERCENT = '0.00%'


def _money(v: float) -> str:
    return f"{v:,.2f} €"


def _pct(v: float) -> str:
    return f"{v:,.2f} %"


def _gain_color(v: float):
    return _GREEN if v >= 0 else _RED


# ── Report Service ──────────────────────────────────────────────────

class ReportService:
    """Service for generating various reports."""

    # ── Portfolio data fetch ────────────────────────────────────────

    async def get_portfolio_data(
        self, db: AsyncSession, user_id: str, year: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Get comprehensive portfolio data for reports."""
        result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == user_id,
            )
        )
        portfolios = result.scalars().all()
        portfolio_ids = [p.id for p in portfolios]

        if not portfolio_ids:
            return {
                "portfolios": [], "assets": [], "transactions": [],
                "summary": {"total_value": 0, "total_invested": 0, "gain_loss": 0, "gain_loss_percent": 0},
            }

        asset_result = await db.execute(
            select(Asset).where(
                Asset.portfolio_id.in_(portfolio_ids),
            )
        )
        assets = asset_result.scalars().all()
        asset_ids = [a.id for a in assets]

        trans_query = select(Transaction).where(Transaction.asset_id.in_(asset_ids))
        if year:
            trans_query = trans_query.where(
                Transaction.executed_at >= datetime(year, 1, 1),
                Transaction.executed_at <= datetime(year, 12, 31, 23, 59, 59),
            )
        trans_query = trans_query.order_by(Transaction.executed_at.desc())
        trans_result = await db.execute(trans_query)
        transactions = trans_result.scalars().all()

        # Fetch prices
        crypto_symbols = [a.symbol for a in assets if a.asset_type == AssetType.CRYPTO]
        prices_map = {}
        if crypto_symbols:
            try:
                prices_map = await price_service.get_multiple_crypto_prices(crypto_symbols)
            except Exception:
                pass

        total_value = 0
        total_invested = 0
        asset_reports = []

        for asset in assets:
            quantity = float(asset.quantity)
            avg_price = float(asset.avg_buy_price)
            price_data = prices_map.get(asset.symbol.upper())
            current_price = float(price_data["price"]) if price_data and price_data.get("price") else avg_price

            invested = quantity * avg_price
            current_val = quantity * current_price
            gain = current_val - invested
            gain_pct = (gain / invested * 100) if invested > 0 else 0

            total_invested += invested
            total_value += current_val

            asset_reports.append(AssetReport(
                symbol=asset.symbol, name=asset.name or asset.symbol,
                asset_type=asset.asset_type.value, quantity=quantity,
                avg_buy_price=avg_price, current_price=current_price,
                total_invested=invested, current_value=current_val,
                gain_loss=gain, gain_loss_percent=gain_pct,
            ))

        total_gain = total_value - total_invested
        total_gain_pct = (total_gain / total_invested * 100) if total_invested > 0 else 0

        asset_report_map = {ar.symbol: ar for ar in asset_reports}
        portfolio_summaries = []
        for portfolio in portfolios:
            p_assets = [a for a in assets if a.portfolio_id == portfolio.id]
            p_invested = sum(asset_report_map[a.symbol].total_invested for a in p_assets if a.symbol in asset_report_map)
            p_value = sum(asset_report_map[a.symbol].current_value for a in p_assets if a.symbol in asset_report_map)
            p_gain = p_value - p_invested
            p_gain_pct = (p_gain / p_invested * 100) if p_invested > 0 else 0
            portfolio_summaries.append(PortfolioSummary(
                name=portfolio.name, total_value=p_value, total_invested=p_invested,
                gain_loss=p_gain, gain_loss_percent=p_gain_pct, asset_count=len(p_assets),
            ))

        asset_map = {a.id: a for a in assets}
        tax_transactions = []
        for trans in transactions:
            asset = asset_map.get(trans.asset_id)
            if asset:
                tax_transactions.append(TaxTransaction(
                    date=trans.executed_at, symbol=asset.symbol,
                    transaction_type=trans.transaction_type.value,
                    quantity=float(trans.quantity), price=float(trans.price),
                    total=float(trans.quantity) * float(trans.price),
                    fee=float(trans.fee) if trans.fee else 0, gain_loss=None,
                ))

        return {
            "portfolios": portfolio_summaries, "assets": asset_reports,
            "transactions": tax_transactions,
            "summary": {
                "total_value": total_value, "total_invested": total_invested,
                "gain_loss": total_gain, "gain_loss_percent": total_gain_pct,
            },
            "generated_at": datetime.utcnow(), "year": year,
        }

    # ── Tax 2086 computation ────────────────────────────────────────

    async def compute_tax_2086(
        self, db: AsyncSession, user_id: str, year: int,
    ) -> TaxSummary2086:
        """Compute capital gains per French 2086 formula.

        Formula per cession:
          PV = Prix_cession − (Total_acquisition × Prix_cession / Valeur_portefeuille)

        Where:
          - Prix_cession = qty × price − fees
          - Total_acquisition = cumulative cost of all buys up to this point
          - Valeur_portefeuille = total portfolio value at the moment of cession
        """
        # 1. Get ALL crypto assets for this user
        result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == user_id,
            )
        )
        portfolios = result.scalars().all()
        portfolio_ids = [p.id for p in portfolios]

        if not portfolio_ids:
            return TaxSummary2086(
                year=year, total_cessions=0, total_acquisitions_fraction=0,
                total_plus_values=0, total_moins_values=0, net_plus_value=0,
                nb_cessions=0, nb_court_terme=0, nb_long_terme=0,
                flat_tax_30=0, ir_12_8=0, ps_17_2=0, events=[],
            )

        asset_result = await db.execute(
            select(Asset).where(
                Asset.portfolio_id.in_(portfolio_ids),
            )
        )
        assets = asset_result.scalars().all()
        crypto_assets = [a for a in assets if a.asset_type == AssetType.CRYPTO]
        crypto_asset_ids = [a.id for a in crypto_assets]

        if not crypto_asset_ids:
            return TaxSummary2086(
                year=year, total_cessions=0, total_acquisitions_fraction=0,
                total_plus_values=0, total_moins_values=0, net_plus_value=0,
                nb_cessions=0, nb_court_terme=0, nb_long_terme=0,
                flat_tax_30=0, ir_12_8=0, ps_17_2=0, events=[],
            )

        # 2. Get ALL transactions (all years) ordered chronologically
        trans_result = await db.execute(
            select(Transaction).where(
                Transaction.asset_id.in_(crypto_asset_ids),
            ).order_by(Transaction.executed_at.asc())
        )
        all_transactions = trans_result.scalars().all()

        asset_map = {a.id: a for a in crypto_assets}

        # 3. Reconstruct portfolio history chronologically
        # Track: holdings (symbol → qty), total_acquisition_cost, first_buy_date per symbol
        holdings: Dict[str, Decimal] = {}      # symbol → quantity
        cost_basis: Dict[str, Decimal] = {}    # symbol → total cost for that symbol
        first_buy: Dict[str, datetime] = {}    # symbol → first acquisition date
        total_acquisition_cost = Decimal("0")  # global PMP numerator

        buy_types = {
            TransactionType.BUY, TransactionType.TRANSFER_IN,
            TransactionType.AIRDROP, TransactionType.STAKING_REWARD,
            TransactionType.CONVERSION_IN,
        }
        sell_types = {
            TransactionType.SELL, TransactionType.CONVERSION_OUT,
            TransactionType.TRANSFER_OUT,
        }

        year_start = datetime(year, 1, 1)
        year_end = datetime(year, 12, 31, 23, 59, 59)

        events: List[TaxEvent2086] = []

        for tx in all_transactions:
            asset = asset_map.get(tx.asset_id)
            if not asset:
                continue

            symbol = asset.symbol
            qty = Decimal(str(tx.quantity))
            price = Decimal(str(tx.price))
            fee = Decimal(str(tx.fee or 0))
            tx_type = tx.transaction_type

            if tx_type in buy_types:
                # Acquisition
                tx_cost = qty * price + fee
                holdings[symbol] = holdings.get(symbol, Decimal("0")) + qty
                cost_basis[symbol] = cost_basis.get(symbol, Decimal("0")) + tx_cost
                total_acquisition_cost += tx_cost

                if symbol not in first_buy:
                    first_buy[symbol] = tx.executed_at

            elif tx_type in sell_types:
                # Cession — only SELL and CONVERSION_OUT are taxable events
                # TRANSFER_OUT is not a taxable cession (just moving assets)
                is_taxable = tx_type in {TransactionType.SELL, TransactionType.CONVERSION_OUT}

                cession_price = qty * price - fee

                if is_taxable and year_start <= tx.executed_at <= year_end:
                    # Compute portfolio value at this moment
                    # We use the current holdings × the price at which this cession occurs
                    # as a proxy. In reality, you'd need all prices at this exact moment.
                    # The simplest correct approach: use the cost basis as proxy for
                    # "valeur globale du portefeuille" when we don't have exact prices.
                    # Better approach: sum all holdings × their last known prices.
                    # For now, use the sum of cost_basis as the portfolio value proxy,
                    # adjusted by the ratio of current cession price to cost basis.
                    #
                    # Actually, the correct 2086 approach:
                    # Valeur_portefeuille = sum of all crypto holdings at market price
                    # at the time of cession. We approximate using cost_basis for unsold
                    # assets and market price for the asset being sold.
                    portfolio_value = Decimal("0")
                    for sym, qty_held in holdings.items():
                        if qty_held > 0:
                            if sym == symbol:
                                # Use the cession price for this asset
                                portfolio_value += qty_held * price
                            else:
                                # Use cost basis / quantity as proxy
                                sym_qty = holdings.get(sym, Decimal("0"))
                                sym_cost = cost_basis.get(sym, Decimal("0"))
                                if sym_qty > 0:
                                    portfolio_value += sym_cost  # cost basis as proxy

                    # The 2086 formula
                    if portfolio_value > 0:
                        acquisition_fraction = float(total_acquisition_cost) * float(cession_price) / float(portfolio_value)
                    else:
                        acquisition_fraction = 0.0

                    gain_loss = float(cession_price) - acquisition_fraction

                    # Holding period
                    fb = first_buy.get(symbol)
                    if fb and (tx.executed_at - fb).days >= 730:  # >= 2 years
                        holding = "long_terme"
                    else:
                        holding = "court_terme"

                    events.append(TaxEvent2086(
                        date=tx.executed_at,
                        symbol=symbol,
                        event_type=tx_type.value,
                        quantity=float(qty),
                        unit_price=float(price),
                        cession_price=float(cession_price),
                        portfolio_value=float(portfolio_value),
                        total_acquisition_cost=float(total_acquisition_cost),
                        acquisition_fraction=acquisition_fraction,
                        gain_loss=gain_loss,
                        holding_period=holding,
                        fees=float(fee),
                    ))

                # Update holdings and reduce acquisition cost proportionally
                held = holdings.get(symbol, Decimal("0"))
                if held > 0:
                    fraction_sold = min(qty / held, Decimal("1"))
                    cost_reduction = cost_basis.get(symbol, Decimal("0")) * fraction_sold
                    cost_basis[symbol] = cost_basis.get(symbol, Decimal("0")) - cost_reduction
                    total_acquisition_cost -= cost_reduction

                holdings[symbol] = max(Decimal("0"), holdings.get(symbol, Decimal("0")) - qty)

        # 4. Build summary
        total_cessions = sum(e.cession_price for e in events)
        total_acq_fraction = sum(e.acquisition_fraction for e in events)
        total_pv = sum(e.gain_loss for e in events if e.gain_loss > 0)
        total_mv = sum(e.gain_loss for e in events if e.gain_loss < 0)
        net_pv = total_pv + total_mv  # total_mv is negative
        nb_ct = sum(1 for e in events if e.holding_period == "court_terme")
        nb_lt = sum(1 for e in events if e.holding_period == "long_terme")

        # Flat tax only applies if net_plus_value > 0
        taxable = max(0, net_pv)
        ir = taxable * 0.128
        ps = taxable * 0.172
        flat_tax = ir + ps

        return TaxSummary2086(
            year=year,
            total_cessions=total_cessions,
            total_acquisitions_fraction=total_acq_fraction,
            total_plus_values=total_pv,
            total_moins_values=total_mv,
            net_plus_value=net_pv,
            nb_cessions=len(events),
            nb_court_terme=nb_ct,
            nb_long_terme=nb_lt,
            flat_tax_30=flat_tax,
            ir_12_8=ir,
            ps_17_2=ps,
            events=events,
        )

    # ── Performance PDF ─────────────────────────────────────────────

    def generate_performance_pdf(self, data: Dict[str, Any]) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm,
        )
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('T', parent=styles['Heading1'], fontSize=24, spaceAfter=30, textColor=_BLUE)
        heading_style = ParagraphStyle('H', parent=styles['Heading2'], fontSize=14, spaceBefore=20, spaceAfter=10, textColor=_DARK_BLUE)
        normal_style = styles['Normal']
        elements = []

        elements.append(Paragraph("Rapport de Performance", title_style))
        elements.append(Paragraph(f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}", normal_style))
        elements.append(Spacer(1, 20))

        summary = data.get("summary", {})
        elements.append(Paragraph("Résumé Global", heading_style))
        summary_data = [
            ["Indicateur", "Valeur"],
            ["Valeur totale", _money(summary.get('total_value', 0))],
            ["Total investi", _money(summary.get('total_invested', 0))],
            ["Plus/Moins-value", _money(summary.get('gain_loss', 0))],
            ["Performance", _pct(summary.get('gain_loss_percent', 0))],
        ]
        t = Table(summary_data, colWidths=[8*cm, 6*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), _BLUE), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11), ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), _LIGHT_BG), ('GRID', (0, 0), (-1, -1), 1, _BORDER_COLOR),
            ('FONTSIZE', (0, 1), (-1, -1), 10), ('TOPPADDING', (0, 1), (-1, -1), 8), ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 20))

        # Portfolios
        portfolios = data.get("portfolios", [])
        if portfolios:
            elements.append(Paragraph("Portefeuilles", heading_style))
            rows = [["Nom", "Valeur", "Investi", "+/- Value", "Perf.", "Actifs"]]
            for p in portfolios:
                rows.append([p.name, _money(p.total_value), _money(p.total_invested), _money(p.gain_loss), _pct(p.gain_loss_percent), str(p.asset_count)])
            t = Table(rows, colWidths=[4*cm, 2.8*cm, 2.8*cm, 2.5*cm, 2*cm, 1.5*cm])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), _BLUE), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (1, 0), (-1, -1), 'RIGHT'), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9), ('GRID', (0, 0), (-1, -1), 1, _BORDER_COLOR),
                ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, _LIGHT_BG]),
            ]))
            elements.append(t)
            elements.append(Spacer(1, 20))

        # Assets
        assets = data.get("assets", [])
        if assets:
            elements.append(Paragraph("Détail des Actifs", heading_style))
            rows = [["Symbole", "Type", "Qté", "PRU", "Valeur", "+/- Value", "Perf."]]
            for a in assets:
                rows.append([a.symbol, a.asset_type.upper()[:6], f"{a.quantity:,.4f}", _money(a.avg_buy_price), _money(a.current_value), _money(a.gain_loss), _pct(a.gain_loss_percent)])
            t = Table(rows, colWidths=[2.2*cm, 1.8*cm, 2*cm, 2.5*cm, 2.8*cm, 2.5*cm, 1.8*cm])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), _BLUE), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (2, 0), (-1, -1), 'RIGHT'), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8), ('GRID', (0, 0), (-1, -1), 1, _BORDER_COLOR),
                ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, _LIGHT_BG]),
            ]))
            elements.append(t)

        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()

    # ── Performance Excel ───────────────────────────────────────────

    def generate_performance_excel(self, data: Dict[str, Any]) -> bytes:
        wb = Workbook()

        # Summary
        ws = wb.active
        ws.title = "Résumé"
        summary = data.get("summary", {})
        ws['A1'] = "Rapport de Performance InvestAI"
        ws['A1'].font = Font(bold=True, size=16)
        ws['A2'] = f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}"

        for cell_ref in ['A4', 'B4']:
            ws[cell_ref].font = _XL_HEADER_FONT
            ws[cell_ref].fill = _XL_HEADER_FILL
        ws['A4'] = "Indicateur"
        ws['B4'] = "Valeur"

        rows = [
            ("Valeur totale", summary.get('total_value', 0)),
            ("Total investi", summary.get('total_invested', 0)),
            ("Plus/Moins-value", summary.get('gain_loss', 0)),
            ("Performance (%)", summary.get('gain_loss_percent', 0) / 100),
        ]
        for i, (label, value) in enumerate(rows, start=5):
            ws[f'A{i}'] = label
            ws[f'B{i}'] = value
            ws[f'B{i}'].number_format = _XL_MONEY if i < 8 else _XL_PERCENT

        ws.column_dimensions['A'].width = 20
        ws.column_dimensions['B'].width = 18

        # Portfolios
        portfolios = data.get("portfolios", [])
        if portfolios:
            ws2 = wb.create_sheet("Portefeuilles")
            headers = ["Nom", "Valeur", "Investi", "+/- Value", "Performance", "Nb Actifs"]
            for col, h in enumerate(headers, 1):
                c = ws2.cell(row=1, column=col, value=h)
                c.font = _XL_HEADER_FONT
                c.fill = _XL_HEADER_FILL
                c.border = _XL_BORDER
            for row, p in enumerate(portfolios, 2):
                ws2.cell(row=row, column=1, value=p.name).border = _XL_BORDER
                ws2.cell(row=row, column=2, value=p.total_value).number_format = _XL_MONEY
                ws2.cell(row=row, column=3, value=p.total_invested).number_format = _XL_MONEY
                ws2.cell(row=row, column=4, value=p.gain_loss).number_format = _XL_MONEY
                ws2.cell(row=row, column=5, value=p.gain_loss_percent / 100).number_format = _XL_PERCENT
                ws2.cell(row=row, column=6, value=p.asset_count)
                for col in range(1, 7):
                    ws2.cell(row=row, column=col).border = _XL_BORDER
            for col in range(1, 7):
                ws2.column_dimensions[get_column_letter(col)].width = 15

        # Assets
        assets = data.get("assets", [])
        if assets:
            ws3 = wb.create_sheet("Actifs")
            headers = ["Symbole", "Nom", "Type", "Quantité", "PRU", "Prix actuel", "Investi", "Valeur", "+/- Value", "Perf."]
            for col, h in enumerate(headers, 1):
                c = ws3.cell(row=1, column=col, value=h)
                c.font = _XL_HEADER_FONT
                c.fill = _XL_HEADER_FILL
                c.border = _XL_BORDER
            for row, a in enumerate(assets, 2):
                vals = [a.symbol, a.name, a.asset_type, a.quantity, a.avg_buy_price, a.current_price, a.total_invested, a.current_value, a.gain_loss, a.gain_loss_percent / 100]
                for col, v in enumerate(vals, 1):
                    c = ws3.cell(row=row, column=col, value=v)
                    c.border = _XL_BORDER
                    if col in (5, 6, 7, 8, 9):
                        c.number_format = _XL_MONEY
                    elif col == 10:
                        c.number_format = _XL_PERCENT
            for col in range(1, 11):
                ws3.column_dimensions[get_column_letter(col)].width = 14

        # Transactions
        transactions = data.get("transactions", [])
        if transactions:
            ws4 = wb.create_sheet("Transactions")
            headers = ["Date", "Symbole", "Type", "Quantité", "Prix", "Total", "Frais"]
            for col, h in enumerate(headers, 1):
                c = ws4.cell(row=1, column=col, value=h)
                c.font = _XL_HEADER_FONT
                c.fill = _XL_HEADER_FILL
                c.border = _XL_BORDER
            for row, t in enumerate(transactions, 2):
                ws4.cell(row=row, column=1, value=t.date.strftime('%d/%m/%Y')).border = _XL_BORDER
                ws4.cell(row=row, column=2, value=t.symbol).border = _XL_BORDER
                ws4.cell(row=row, column=3, value=t.transaction_type).border = _XL_BORDER
                ws4.cell(row=row, column=4, value=t.quantity).border = _XL_BORDER
                ws4.cell(row=row, column=5, value=t.price).number_format = _XL_MONEY
                ws4.cell(row=row, column=6, value=t.total).number_format = _XL_MONEY
                ws4.cell(row=row, column=7, value=t.fee).number_format = _XL_MONEY
                for col in range(1, 8):
                    ws4.cell(row=row, column=col).border = _XL_BORDER
            for col in range(1, 8):
                ws4.column_dimensions[get_column_letter(col)].width = 14

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()

    # ── Tax 2086 PDF ────────────────────────────────────────────────

    async def generate_tax_report_2086(
        self, db: AsyncSession, user_id: str, year: int,
    ) -> bytes:
        """Generate French tax report 2086 for crypto assets with real capital gains."""
        tax = await self.compute_tax_2086(db, user_id, year)

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm,
        )
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('T', parent=styles['Heading1'], fontSize=20, spaceAfter=20, textColor=_BLUE)
        heading_style = ParagraphStyle('H', parent=styles['Heading2'], fontSize=12, spaceBefore=15, spaceAfter=8, textColor=_DARK_BLUE)
        info_style = ParagraphStyle('I', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#64748b'))
        small_style = ParagraphStyle('S', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#64748b'))

        elements = []

        # ── Title ───────────────────────────────────────────────────
        elements.append(Paragraph(f"Déclaration Fiscale Crypto — Année {year}", title_style))
        elements.append(Paragraph("Formulaire 2086 — Plus-values sur actifs numériques", heading_style))
        elements.append(Paragraph(
            f"Document généré le {datetime.now().strftime('%d/%m/%Y')} — À usage indicatif uniquement", info_style
        ))
        elements.append(Spacer(1, 20))

        # ── 1. Résumé des cessions ──────────────────────────────────
        elements.append(Paragraph("1. Résumé des cessions", heading_style))

        summary_rows = [
            ["Description", "Montant"],
            ["Nombre de cessions", str(tax.nb_cessions)],
            ["  dont court terme (< 2 ans)", str(tax.nb_court_terme)],
            ["  dont long terme (≥ 2 ans)", str(tax.nb_long_terme)],
            ["Prix total de cession", _money(tax.total_cessions)],
            ["Fraction d'acquisition (PMP)", _money(tax.total_acquisitions_fraction)],
            ["Total plus-values", _money(tax.total_plus_values)],
            ["Total moins-values", _money(tax.total_moins_values)],
            ["Plus-value nette imposable", _money(tax.net_plus_value)],
        ]

        t = Table(summary_rows, colWidths=[10*cm, 5*cm])
        style_cmds = [
            ('BACKGROUND', (0, 0), (-1, 0), _BLUE), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10), ('GRID', (0, 0), (-1, -1), 1, _BORDER_COLOR),
            ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            # Highlight net PV row
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ]
        if tax.net_plus_value >= 0:
            style_cmds.append(('TEXTCOLOR', (1, -1), (1, -1), _GREEN))
        else:
            style_cmds.append(('TEXTCOLOR', (1, -1), (1, -1), _RED))
        t.setStyle(TableStyle(style_cmds))
        elements.append(t)
        elements.append(Spacer(1, 20))

        # ── 2. Estimation fiscale ───────────────────────────────────
        elements.append(Paragraph("2. Estimation de l'imposition (PFU — Flat Tax 30%)", heading_style))

        tax_rows = [
            ["Composante", "Taux", "Montant"],
            ["Plus-value nette imposable", "", _money(max(0, tax.net_plus_value))],
            ["Impôt sur le revenu", "12,8%", _money(tax.ir_12_8)],
            ["Prélèvements sociaux", "17,2%", _money(tax.ps_17_2)],
            ["Total PFU (Flat Tax)", "30,0%", _money(tax.flat_tax_30)],
        ]

        t = Table(tax_rows, colWidths=[8*cm, 3*cm, 4*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), _BLUE), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10), ('GRID', (0, 0), (-1, -1), 1, _BORDER_COLOR),
            ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#fef3c7')),
        ]))
        elements.append(t)

        if tax.net_plus_value <= 0:
            elements.append(Spacer(1, 5))
            elements.append(Paragraph(
                "Aucune imposition : la plus-value nette est négative ou nulle.", info_style
            ))

        elements.append(Spacer(1, 20))

        # ── 3. Détail des cessions ──────────────────────────────────
        if tax.events:
            elements.append(Paragraph("3. Détail des cessions", heading_style))
            elements.append(Paragraph(
                "Calcul selon la formule 2086 : PV = Prix cession − (Coût acquisition global × Prix cession / Valeur portefeuille)",
                small_style,
            ))
            elements.append(Spacer(1, 8))

            header = ["Date", "Actif", "Type", "Qté", "Prix cession", "Fraction acq.", "PV/MV", "Durée"]
            rows = [header]
            for e in sorted(tax.events, key=lambda x: x.date):
                type_label = "Conv." if e.event_type == "conversion_out" else "Vente"
                duration = "≥2 ans" if e.holding_period == "long_terme" else "<2 ans"
                rows.append([
                    e.date.strftime('%d/%m/%Y'),
                    e.symbol,
                    type_label,
                    f"{e.quantity:,.6f}",
                    _money(e.cession_price),
                    _money(e.acquisition_fraction),
                    _money(e.gain_loss),
                    duration,
                ])

            t = Table(rows, colWidths=[2*cm, 1.6*cm, 1.4*cm, 2*cm, 2.4*cm, 2.4*cm, 2.2*cm, 1.6*cm])
            style_cmds = [
                ('BACKGROUND', (0, 0), (-1, 0), _BLUE), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (3, 0), (-1, -1), 'RIGHT'), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 7), ('GRID', (0, 0), (-1, -1), 1, _BORDER_COLOR),
                ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, _LIGHT_BG]),
            ]
            # Color gain/loss column
            for i, e in enumerate(sorted(tax.events, key=lambda x: x.date), 1):
                c = _GREEN if e.gain_loss >= 0 else _RED
                style_cmds.append(('TEXTCOLOR', (6, i), (6, i), c))
            t.setStyle(TableStyle(style_cmds))
            elements.append(t)
        else:
            elements.append(Paragraph(
                "Aucune cession d'actifs numériques enregistrée pour cette année.", info_style
            ))

        elements.append(Spacer(1, 30))

        # ── 4. Mentions légales ─────────────────────────────────────
        elements.append(Paragraph("Mentions importantes", heading_style))
        elements.append(Paragraph(
            "Ce document est fourni à titre indicatif uniquement et ne constitue pas un conseil fiscal. "
            "Veuillez consulter un professionnel pour votre déclaration officielle. "
            "Les plus-values sur actifs numériques sont soumises au prélèvement forfaitaire unique (PFU) de 30% "
            "(12,8% d'impôt sur le revenu + 17,2% de prélèvements sociaux) ou au barème progressif de l'impôt sur le revenu sur option. "
            "Le calcul utilise la méthode du Prix Moyen Pondéré (PMP) global du portefeuille conformément à l'article 150 VH bis du CGI. "
            "La valeur du portefeuille au moment de chaque cession est estimée à partir des données disponibles.",
            info_style,
        ))

        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()

    # ── Tax Excel ───────────────────────────────────────────────────

    async def generate_tax_excel(
        self, db: AsyncSession, user_id: str, year: int,
    ) -> bytes:
        """Generate Excel file for tax reporting with full 2086 calculations."""
        tax = await self.compute_tax_2086(db, user_id, year)

        wb = Workbook()

        # ── Résumé sheet ────────────────────────────────────────────
        ws = wb.active
        ws.title = f"Résumé {year}"

        ws['A1'] = f"Déclaration Fiscale Crypto — Année {year}"
        ws['A1'].font = Font(bold=True, size=14)
        ws['A2'] = f"Généré le {datetime.now().strftime('%d/%m/%Y')}"
        ws['A2'].font = Font(italic=True, color="666666")

        # Summary data
        ws['A4'] = "Résumé des cessions"
        ws['A4'].font = Font(bold=True, size=12)

        summary_items = [
            ("Nombre de cessions", tax.nb_cessions, None),
            ("  dont court terme (< 2 ans)", tax.nb_court_terme, None),
            ("  dont long terme (≥ 2 ans)", tax.nb_long_terme, None),
            ("Prix total de cession", tax.total_cessions, _XL_MONEY),
            ("Fraction d'acquisition (PMP)", tax.total_acquisitions_fraction, _XL_MONEY),
            ("Total plus-values", tax.total_plus_values, _XL_MONEY),
            ("Total moins-values", tax.total_moins_values, _XL_MONEY),
            ("Plus-value nette imposable", tax.net_plus_value, _XL_MONEY),
        ]
        for i, (label, value, fmt) in enumerate(summary_items, 5):
            ws[f'A{i}'] = label
            ws[f'B{i}'] = value
            if fmt:
                ws[f'B{i}'].number_format = fmt

        # Tax estimation
        row = 5 + len(summary_items) + 1
        ws[f'A{row}'] = "Estimation fiscale (PFU 30%)"
        ws[f'A{row}'].font = Font(bold=True, size=12)

        tax_items = [
            ("Impôt sur le revenu (12,8%)", tax.ir_12_8),
            ("Prélèvements sociaux (17,2%)", tax.ps_17_2),
            ("Total Flat Tax (30%)", tax.flat_tax_30),
        ]
        for i, (label, value) in enumerate(tax_items, row + 1):
            ws[f'A{i}'] = label
            ws[f'B{i}'] = value
            ws[f'B{i}'].number_format = _XL_MONEY
            if label.startswith("Total"):
                ws[f'A{i}'].font = Font(bold=True)
                ws[f'B{i}'].font = Font(bold=True)

        ws.column_dimensions['A'].width = 35
        ws.column_dimensions['B'].width = 18

        # ── Cessions sheet ──────────────────────────────────────────
        ws2 = wb.create_sheet("Cessions")
        headers = ["Date", "Actif", "Type", "Quantité", "Prix unitaire", "Prix cession",
                    "Valeur portefeuille", "Coût acquisition", "Fraction acq.", "PV/MV", "Durée"]
        for col, h in enumerate(headers, 1):
            c = ws2.cell(row=1, column=col, value=h)
            c.font = _XL_HEADER_FONT
            c.fill = _XL_HEADER_FILL
            c.border = _XL_BORDER

        for row, e in enumerate(sorted(tax.events, key=lambda x: x.date), 2):
            type_label = "Conversion" if e.event_type == "conversion_out" else "Vente"
            duration = "≥ 2 ans" if e.holding_period == "long_terme" else "< 2 ans"
            vals = [
                e.date.strftime('%d/%m/%Y'), e.symbol, type_label, e.quantity,
                e.unit_price, e.cession_price, e.portfolio_value,
                e.total_acquisition_cost, e.acquisition_fraction, e.gain_loss, duration,
            ]
            for col, v in enumerate(vals, 1):
                c = ws2.cell(row=row, column=col, value=v)
                c.border = _XL_BORDER
                if col in (5, 6, 7, 8, 9, 10):
                    c.number_format = _XL_MONEY
                if col == 10:
                    c.font = Font(color="16a34a" if e.gain_loss >= 0 else "dc2626")

        for col in range(1, 12):
            ws2.column_dimensions[get_column_letter(col)].width = 16

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()


# Singleton
report_service = ReportService()
