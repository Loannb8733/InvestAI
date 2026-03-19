"""Report generation service for PDF and Excel exports."""

import io
import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from openpyxl import Workbook
from openpyxl.styles import Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction, TransactionType
from app.services.metrics_service import is_liquidity, is_safe_haven, metrics_service
from app.services.snapshot_service import snapshot_service

logger = logging.getLogger(__name__)

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
    breakeven_price: Optional[float] = None
    risk_weight: Optional[float] = None
    total_fees: float = 0.0
    exchange: Optional[str] = None


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
    event_type: str  # "sell" / "conversion_out"
    quantity: float
    unit_price: float
    cession_price: float  # qty × price − fees
    portfolio_value: float  # valeur globale du portefeuille au moment de la cession
    total_acquisition_cost: float  # coût total d'acquisition cumulé
    acquisition_fraction: float  # total_acq × (cession / portfolio_value)
    gain_loss: float  # cession_price − acquisition_fraction
    holding_period: str  # "court_terme" / "long_terme"
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
    flat_tax_30: float  # PFU total
    ir_12_8: float  # Impôt sur le revenu (12.8%)
    ps_17_2: float  # Prélèvements sociaux (17.2%)
    events: List[TaxEvent2086] = field(default_factory=list)


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


def _pct(v: float) -> str:
    return f"{v:,.2f} %"


def _gain_color(v: float):
    return _GREEN if v >= 0 else _RED


# ── Report Service ──────────────────────────────────────────────────


class ReportService:
    """Service for generating various reports."""

    # ── Report data (single source of truth: metrics_service) ──────

    async def get_report_data(
        self,
        db: AsyncSession,
        user_id: str,
        year: Optional[int] = None,
        currency: str = "EUR",
    ) -> Dict[str, Any]:
        """Get comprehensive portfolio data for reports.

        Delegates ALL calculations to metrics_service and snapshot_service.
        This method only reshapes their output into report-friendly structures.
        """
        # 1. Dashboard-level summary (includes pnl_data, allocation)
        dashboard = await metrics_service.get_user_dashboard_metrics(db, user_id, currency=currency)

        # 2. Per-portfolio metrics for detailed asset breakdown
        result = await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))
        portfolios = result.scalars().all()

        if not portfolios:
            return {
                "portfolios": [],
                "assets": [],
                "transactions": [],
                "summary": {
                    "total_value": 0.0,
                    "total_invested": 0.0,
                    "gain_loss": 0.0,
                    "gain_loss_percent": 0.0,
                },
                "pnl_data": {},
                "risk_metrics": {},
                "platform_analysis": [],
                "generated_at": datetime.utcnow(),
                "year": year,
            }

        portfolio_summaries: List[PortfolioSummary] = []
        all_asset_reports: List[AssetReport] = []
        all_asset_ids: List[str] = []

        for portfolio in portfolios:
            pm = await metrics_service.get_portfolio_metrics(db, str(portfolio.id), currency=currency)

            p_value = pm["total_value"]
            p_invested = pm["total_invested"]
            p_gain = p_value - p_invested
            p_gain_pct = (p_gain / p_invested * 100) if p_invested > 0 else 0

            portfolio_summaries.append(
                PortfolioSummary(
                    name=portfolio.name,
                    total_value=p_value,
                    total_invested=p_invested,
                    gain_loss=p_gain,
                    gain_loss_percent=p_gain_pct,
                    asset_count=pm.get("assets_count", len(pm.get("assets", []))),
                )
            )

            for a in pm.get("assets", []):
                all_asset_ids.append(a["id"])
                all_asset_reports.append(
                    AssetReport(
                        symbol=a["symbol"],
                        name=a.get("name") or a["symbol"],
                        asset_type=a["asset_type"],
                        quantity=a["quantity"],
                        avg_buy_price=a["avg_buy_price"],
                        current_price=a.get("current_price") or a["avg_buy_price"],
                        total_invested=a["total_invested"],
                        current_value=a["current_value"],
                        gain_loss=a["gain_loss"],
                        gain_loss_percent=a["gain_loss_percent"],
                        breakeven_price=a.get("breakeven_price"),
                        risk_weight=a.get("risk_weight"),
                        total_fees=a.get("total_fees", 0.0),
                        exchange=a.get("exchange"),
                    )
                )

        # 3. Transaction list (direct query — metrics_service doesn't expose rows)
        tax_transactions: List[TaxTransaction] = []
        if all_asset_ids:
            trans_query = select(Transaction).where(Transaction.asset_id.in_(all_asset_ids))
            if year:
                trans_query = trans_query.where(
                    Transaction.executed_at >= datetime(year, 1, 1),
                    Transaction.executed_at <= datetime(year, 12, 31, 23, 59, 59),
                )
            trans_query = trans_query.order_by(Transaction.executed_at.desc())
            trans_result = await db.execute(trans_query)
            transactions = trans_result.scalars().all()

            # Build asset id → symbol map from DB
            asset_id_result = await db.execute(select(Asset.id, Asset.symbol).where(Asset.id.in_(all_asset_ids)))
            id_to_symbol = {str(row[0]): row[1] for row in asset_id_result.all()}

            for trans in transactions:
                symbol = id_to_symbol.get(str(trans.asset_id), "")
                if symbol:
                    tax_transactions.append(
                        TaxTransaction(
                            date=trans.executed_at,
                            symbol=symbol,
                            transaction_type=trans.transaction_type.value,
                            quantity=float(trans.quantity),
                            price=float(trans.price),
                            total=float(trans.quantity) * float(trans.price),
                            fee=float(trans.fee) if trans.fee else 0,
                            gain_loss=None,
                        )
                    )

        # 4. Risk metrics (for Excel "Analyse de Risque" sheet)
        # Use the same allocations as the Dashboard (filtered: current_value > 0)
        # and the same days resolution (days=0 → actual days since first tx)
        # to ensure HHI, VaR, etc. match exactly.
        risk_metrics: Dict[str, Any] = {}
        try:
            allocations = [
                {"symbol": a["symbol"], "value": a["current_value"]} for a in dashboard.get("aggregated_assets", [])
            ]
            # Resolve days like the Dashboard does for days=0 ("all time")
            first_tx_result = await db.execute(
                select(func.min(Transaction.executed_at)).where(Transaction.asset_id.in_(all_asset_ids))
            )
            first_tx_date = first_tx_result.scalar()
            if first_tx_date:
                if hasattr(first_tx_date, "tzinfo") and first_tx_date.tzinfo is not None:
                    first_tx_date = first_tx_date.replace(tzinfo=None)
                risk_days = max((datetime.utcnow() - first_tx_date).days + 1, 7)
            else:
                risk_days = 30

            risk_metrics = await snapshot_service.get_all_risk_metrics(
                db,
                user_id,
                current_value=dashboard["total_value"],
                allocations=allocations,
                days=risk_days,
            )
        except Exception:
            logger.warning("Failed to compute risk metrics for report", exc_info=True)

        # 5. Platform analysis (GROUP BY exchange)
        platform_map: Dict[str, Dict[str, Any]] = {}
        for ar in all_asset_reports:
            ex = ar.exchange or "Autre"
            if ex not in platform_map:
                platform_map[ex] = {
                    "exchange": ex,
                    "total_value": 0.0,
                    "total_invested": 0.0,
                    "total_fees": 0.0,
                    "count": 0,
                }
            platform_map[ex]["total_value"] += ar.current_value
            platform_map[ex]["total_invested"] += ar.total_invested
            platform_map[ex]["total_fees"] += ar.total_fees
            platform_map[ex]["count"] += 1

        platform_analysis = []
        for p in platform_map.values():
            invested = p["total_invested"]
            p["roi_percent"] = ((p["total_value"] - invested) / invested * 100) if invested > 0 else 0
            p["net_pnl"] = p["total_value"] - invested - p["total_fees"]
            platform_analysis.append(p)
        platform_analysis.sort(key=lambda x: x["total_value"], reverse=True)

        # 6. Attribution: Alpha / Beta (BTC) / Protection (Or) / Fixed Income / Munitions
        attribution = {"alpha": 0.0, "beta": 0.0, "protection": 0.0, "fixed_income": 0.0, "munitions": 0.0}
        for ar in all_asset_reports:
            sym = ar.symbol.upper()
            if is_liquidity(sym):
                attribution["munitions"] += ar.current_value
            elif getattr(ar, "asset_type", "") == "crowdfunding":
                attribution["fixed_income"] += ar.current_value
            elif sym == "BTC":
                attribution["beta"] += ar.current_value
            elif is_safe_haven(sym):
                attribution["protection"] += ar.current_value
            else:
                attribution["alpha"] += ar.current_value

        # 7. Cash flows (deposits are NOT gains)
        cash_flows = {"total_deposits": 0.0, "total_withdrawals": 0.0}
        for tx in tax_transactions:
            tt = tx.transaction_type
            if tt in {"buy", "transfer_in"}:
                cash_flows["total_deposits"] += tx.total
            elif tt == "sell":
                cash_flows["total_withdrawals"] += tx.total
        cash_flows["net_flows"] = cash_flows["total_deposits"] - cash_flows["total_withdrawals"]

        # 8. Build result
        pnl_data = dashboard.get("pnl_data", {})

        return {
            "portfolios": portfolio_summaries,
            "assets": all_asset_reports,
            "transactions": tax_transactions,
            "summary": {
                "total_value": dashboard["total_value"],
                "total_invested": dashboard["total_invested"],
                "gain_loss": dashboard.get("net_gain_loss", 0),
                "gain_loss_percent": dashboard.get("net_gain_loss_percent", 0),
            },
            "pnl_data": pnl_data,
            "risk_metrics": risk_metrics,
            "platform_analysis": platform_analysis,
            "attribution": attribution,
            "cash_flows": cash_flows,
            "generated_at": datetime.utcnow(),
            "year": year,
        }

    # ── Tax 2086 computation ────────────────────────────────────────

    async def compute_tax_2086(
        self,
        db: AsyncSession,
        user_id: str,
        year: int,
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
                year=year,
                total_cessions=0,
                total_acquisitions_fraction=0,
                total_plus_values=0,
                total_moins_values=0,
                net_plus_value=0,
                nb_cessions=0,
                nb_court_terme=0,
                nb_long_terme=0,
                flat_tax_30=0,
                ir_12_8=0,
                ps_17_2=0,
                events=[],
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
                year=year,
                total_cessions=0,
                total_acquisitions_fraction=0,
                total_plus_values=0,
                total_moins_values=0,
                net_plus_value=0,
                nb_cessions=0,
                nb_court_terme=0,
                nb_long_terme=0,
                flat_tax_30=0,
                ir_12_8=0,
                ps_17_2=0,
                events=[],
            )

        # 2. Get ALL transactions (all years) ordered chronologically
        trans_result = await db.execute(
            select(Transaction)
            .where(
                Transaction.asset_id.in_(crypto_asset_ids),
            )
            .order_by(Transaction.executed_at.asc())
        )
        all_transactions = trans_result.scalars().all()

        asset_map = {a.id: a for a in crypto_assets}

        # 3. Reconstruct portfolio history chronologically
        # Track: holdings (symbol → qty), total_acquisition_cost, first_buy_date per symbol
        holdings: Dict[str, Decimal] = {}  # symbol → quantity
        cost_basis: Dict[str, Decimal] = {}  # symbol → total cost for that symbol
        first_buy: Dict[str, datetime] = {}  # symbol → first acquisition date
        total_acquisition_cost = Decimal("0")  # global PMP numerator

        buy_types = {
            TransactionType.BUY,
            TransactionType.TRANSFER_IN,
            TransactionType.AIRDROP,
            TransactionType.STAKING_REWARD,
            TransactionType.CONVERSION_IN,
        }
        sell_types = {
            TransactionType.SELL,
            TransactionType.CONVERSION_OUT,
            TransactionType.TRANSFER_OUT,
        }

        from datetime import timezone

        year_start = datetime(year, 1, 1, tzinfo=timezone.utc)
        year_end = datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

        events: List[TaxEvent2086] = []

        for tx in all_transactions:
            asset = asset_map.get(tx.asset_id)
            if not asset or not tx.executed_at:
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

                tx_dt = tx.executed_at
                if tx_dt.tzinfo is None:
                    tx_dt = tx_dt.replace(tzinfo=timezone.utc)
                if is_taxable and year_start <= tx_dt <= year_end:
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
                        acquisition_fraction = (
                            float(total_acquisition_cost) * float(cession_price) / float(portfolio_value)
                        )
                    else:
                        acquisition_fraction = 0.0

                    gain_loss = float(cession_price) - acquisition_fraction

                    # Holding period
                    fb = first_buy.get(symbol)
                    if fb and (tx_dt - (fb.replace(tzinfo=timezone.utc) if fb.tzinfo is None else fb)).days >= 730:
                        holding = "long_terme"
                    else:
                        holding = "court_terme"

                    events.append(
                        TaxEvent2086(
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
                        )
                    )

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
            buffer,
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("T", parent=styles["Heading1"], fontSize=24, spaceAfter=30, textColor=_BLUE)
        heading_style = ParagraphStyle(
            "H", parent=styles["Heading2"], fontSize=14, spaceBefore=20, spaceAfter=10, textColor=_DARK_BLUE
        )
        normal_style = styles["Normal"]
        elements = []

        elements.append(Paragraph("Rapport de Performance", title_style))
        elements.append(Paragraph(f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}", normal_style))
        elements.append(Spacer(1, 20))

        summary = data.get("summary", {})
        pnl = data.get("pnl_data", {})
        elements.append(Paragraph("Résumé Global", heading_style))
        summary_data = [
            ["Indicateur", "Valeur"],
            ["Valeur totale", _money(summary.get("total_value", 0))],
            ["Total investi", _money(summary.get("total_invested", 0))],
            ["Plus/Moins-value", _money(summary.get("gain_loss", 0))],
            ["Performance", _pct(summary.get("gain_loss_percent", 0))],
        ]
        if pnl:
            summary_data.extend(
                [
                    ["", ""],
                    ["P&L Latent", _money(pnl.get("unrealized_pnl", 0))],
                    ["P&L Réalisé", _money(pnl.get("realized_pnl", 0))],
                    ["Total Frais", _money(pnl.get("total_fees", 0))],
                    ["P&L Net", _money(pnl.get("net_pnl", 0))],
                ]
            )
        t = Table(summary_data, colWidths=[8 * cm, 6 * cm])
        summary_style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), _BLUE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 11),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
            ("BACKGROUND", (0, 1), (-1, -1), _LIGHT_BG),
            ("GRID", (0, 0), (-1, -1), 1, _BORDER_COLOR),
            ("FONTSIZE", (0, 1), (-1, -1), 10),
            ("TOPPADDING", (0, 1), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 8),
        ]
        if pnl:
            # Bold + color on P&L Net row (last row)
            net_pnl = pnl.get("net_pnl", 0)
            summary_style_cmds.append(("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"))
            summary_style_cmds.append(("TEXTCOLOR", (1, -1), (1, -1), _gain_color(net_pnl)))
        t.setStyle(TableStyle(summary_style_cmds))
        elements.append(t)
        elements.append(Spacer(1, 20))

        # Attribution de performance
        attr = data.get("attribution", {})
        if any(v > 0 for v in attr.values()):
            elements.append(Paragraph("Attribution de Performance", heading_style))
            total_attr = sum(attr.values()) or 1
            attr_data = [
                ["Catégorie", "Valeur", "Poids"],
                ["Alpha (Altcoins)", _money(attr.get("alpha", 0)), _pct(attr.get("alpha", 0) / total_attr * 100)],
                ["Beta (BTC)", _money(attr.get("beta", 0)), _pct(attr.get("beta", 0) / total_attr * 100)],
                [
                    "Protection (Or)",
                    _money(attr.get("protection", 0)),
                    _pct(attr.get("protection", 0) / total_attr * 100),
                ],
                [
                    "Munitions (Cash/Stables)",
                    _money(attr.get("munitions", 0)),
                    _pct(attr.get("munitions", 0) / total_attr * 100),
                ],
            ]
            t = Table(attr_data, colWidths=[6 * cm, 4 * cm, 4 * cm])
            t.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), _BLUE),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 10),
                        ("GRID", (0, 0), (-1, -1), 1, _BORDER_COLOR),
                        ("TOPPADDING", (0, 0), (-1, -1), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                        ("BACKGROUND", (0, 1), (-1, -1), _LIGHT_BG),
                    ]
                )
            )
            elements.append(t)
            elements.append(Spacer(1, 20))

        # Flux de trésorerie (Cash Flows)
        cf = data.get("cash_flows", {})
        if cf.get("total_deposits", 0) > 0 or cf.get("total_withdrawals", 0) > 0:
            elements.append(Paragraph("Flux de Trésorerie", heading_style))
            gain = summary.get("gain_loss", 0)
            cf_data = [
                ["Flux", "Montant"],
                ["Total déposé", _money(cf.get("total_deposits", 0))],
                ["Total retiré", _money(cf.get("total_withdrawals", 0))],
                ["Flux nets (dépôts − retraits)", _money(cf.get("net_flows", 0))],
                ["Plus/Moins-value réelle", _money(gain)],
            ]
            t = Table(cf_data, colWidths=[8 * cm, 6 * cm])
            t.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), _BLUE),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 10),
                        ("GRID", (0, 0), (-1, -1), 1, _BORDER_COLOR),
                        ("TOPPADDING", (0, 0), (-1, -1), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                        ("BACKGROUND", (0, 1), (-1, -1), _LIGHT_BG),
                        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                        ("TEXTCOLOR", (1, -1), (1, -1), _gain_color(gain)),
                    ]
                )
            )
            elements.append(t)
            elements.append(Spacer(1, 20))

        # Portfolios
        portfolios = data.get("portfolios", [])
        if portfolios:
            elements.append(Paragraph("Portefeuilles", heading_style))
            rows = [["Nom", "Valeur", "Investi", "+/- Value", "Perf.", "Actifs"]]
            for p in portfolios:
                rows.append(
                    [
                        p.name,
                        _money(p.total_value),
                        _money(p.total_invested),
                        _money(p.gain_loss),
                        _pct(p.gain_loss_percent),
                        str(p.asset_count),
                    ]
                )
            t = Table(rows, colWidths=[4 * cm, 2.8 * cm, 2.8 * cm, 2.5 * cm, 2 * cm, 1.5 * cm])
            t.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), _BLUE),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("GRID", (0, 0), (-1, -1), 1, _BORDER_COLOR),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _LIGHT_BG]),
                    ]
                )
            )
            elements.append(t)
            elements.append(Spacer(1, 20))

        # Assets
        assets = data.get("assets", [])
        if assets:
            elements.append(Paragraph("Détail des Actifs", heading_style))
            rows = [["Symbole", "Type", "Qté", "PRU", "Valeur", "+/- Value", "Perf.", "Break-even", "Risque"]]
            for a in assets:
                rows.append(
                    [
                        a.symbol,
                        a.asset_type.upper()[:6],
                        f"{a.quantity:,.4f}",
                        _money(a.avg_buy_price),
                        _money(a.current_value),
                        _money(a.gain_loss),
                        _pct(a.gain_loss_percent),
                        _money(a.breakeven_price) if a.breakeven_price else "N/A",
                        f"{a.risk_weight:.1f}%" if a.risk_weight else "N/A",
                    ]
                )
            t = Table(
                rows,
                colWidths=[
                    2.0 * cm,
                    1.5 * cm,
                    1.6 * cm,
                    2.0 * cm,
                    2.2 * cm,
                    2.0 * cm,
                    1.6 * cm,
                    2.0 * cm,
                    1.5 * cm,
                ],
            )
            t.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), _BLUE),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ("GRID", (0, 0), (-1, -1), 1, _BORDER_COLOR),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _LIGHT_BG]),
                    ]
                )
            )
            elements.append(t)

        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()

    # ── Performance Excel ───────────────────────────────────────────

    def generate_performance_excel(self, data: Dict[str, Any]) -> bytes:
        wb = Workbook()

        # ── Résumé sheet ─────────────────────────────────────────────
        ws = wb.active
        ws.title = "Résumé"
        summary = data.get("summary", {})
        pnl = data.get("pnl_data", {})
        ws["A1"] = "Rapport de Performance InvestAI"
        ws["A1"].font = Font(bold=True, size=16)
        ws["A2"] = f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}"

        for cell_ref in ["A4", "B4"]:
            ws[cell_ref].font = _XL_HEADER_FONT
            ws[cell_ref].fill = _XL_HEADER_FILL
        ws["A4"] = "Indicateur"
        ws["B4"] = "Valeur"

        summary_rows = [
            ("Valeur totale", summary.get("total_value", 0), _XL_MONEY),
            ("Total investi", summary.get("total_invested", 0), _XL_MONEY),
            ("Plus/Moins-value", summary.get("gain_loss", 0), _XL_MONEY),
            ("Performance (%)", summary.get("gain_loss_percent", 0) / 100, _XL_PERCENT),
        ]
        if pnl:
            summary_rows.extend(
                [
                    ("", "", None),
                    ("P&L Latent", pnl.get("unrealized_pnl", 0), _XL_MONEY),
                    ("P&L Réalisé", pnl.get("realized_pnl", 0), _XL_MONEY),
                    ("Total Frais", pnl.get("total_fees", 0), _XL_MONEY),
                    ("P&L Net", pnl.get("net_pnl", 0), _XL_MONEY),
                ]
            )
        for i, (label, value, fmt) in enumerate(summary_rows, start=5):
            ws[f"A{i}"] = label
            if value != "":
                ws[f"B{i}"] = value
            if fmt:
                ws[f"B{i}"].number_format = fmt
        # Bold P&L Net row
        if pnl:
            net_row = 5 + len(summary_rows) - 1
            ws[f"A{net_row}"].font = Font(bold=True)
            ws[f"B{net_row}"].font = Font(bold=True)

        ws.column_dimensions["A"].width = 22
        ws.column_dimensions["B"].width = 18

        # ── Portefeuilles sheet ──────────────────────────────────────
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

        # ── Actifs sheet (enrichi) ───────────────────────────────────
        assets = data.get("assets", [])
        if assets:
            ws3 = wb.create_sheet("Actifs")
            headers = [
                "Symbole",
                "Nom",
                "Type",
                "Plateforme",
                "Quantité",
                "PRU",
                "Prix actuel",
                "Break-even",
                "Investi",
                "Valeur",
                "+/- Value",
                "Perf.",
                "Frais",
                "Risque",
            ]
            for col, h in enumerate(headers, 1):
                c = ws3.cell(row=1, column=col, value=h)
                c.font = _XL_HEADER_FONT
                c.fill = _XL_HEADER_FILL
                c.border = _XL_BORDER
            money_cols = {6, 7, 8, 9, 10, 11, 13}  # PRU, Prix, Break-even, Investi, Valeur, +/-, Frais
            pct_cols = {12, 14}  # Perf., Risque
            for row, a in enumerate(assets, 2):
                vals = [
                    a.symbol,
                    a.name,
                    a.asset_type,
                    a.exchange or "",
                    a.quantity,
                    a.avg_buy_price,
                    a.current_price,
                    a.breakeven_price if a.breakeven_price else "",
                    a.total_invested,
                    a.current_value,
                    a.gain_loss,
                    a.gain_loss_percent / 100,
                    a.total_fees,
                    a.risk_weight / 100 if a.risk_weight else "",
                ]
                for col, v in enumerate(vals, 1):
                    c = ws3.cell(row=row, column=col, value=v)
                    c.border = _XL_BORDER
                    if col in money_cols and v != "":
                        c.number_format = _XL_MONEY
                    elif col in pct_cols and v != "":
                        c.number_format = _XL_PERCENT
            for col in range(1, len(headers) + 1):
                ws3.column_dimensions[get_column_letter(col)].width = 14

        # ── Transactions sheet ───────────────────────────────────────
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
                date_str = t.date.strftime("%d/%m/%Y") if t.date else ""
                ws4.cell(row=row, column=1, value=date_str).border = _XL_BORDER
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

        # ── Analyse de Risque sheet ──────────────────────────────────
        risk = data.get("risk_metrics", {})
        if risk:
            ws_risk = wb.create_sheet("Analyse de Risque")
            for cell_ref in ["A1", "B1"]:
                ws_risk[cell_ref].font = _XL_HEADER_FONT
                ws_risk[cell_ref].fill = _XL_HEADER_FILL
                ws_risk[cell_ref].border = _XL_BORDER
            ws_risk["A1"] = "Indicateur"
            ws_risk["B1"] = "Valeur"

            mdd = risk.get("max_drawdown", {})
            var95 = risk.get("var_95", {})
            conc = risk.get("concentration", {})
            st20 = risk.get("stress_test_20", {})
            st40 = risk.get("stress_test_40", {})

            risk_rows = [
                ("Volatilité annualisée", risk.get("volatility", 0) / 100, _XL_PERCENT),
                ("Ratio de Sharpe", risk.get("sharpe_ratio", 0), "0.00"),
                ("Max Drawdown", mdd.get("max_drawdown_percent", 0) / 100, _XL_PERCENT),
                ("Max Drawdown — Pic", mdd.get("peak_date", ""), None),
                ("Max Drawdown — Creux", mdd.get("trough_date", ""), None),
                ("VaR 95% (%)", var95.get("var_percent", 0) / 100, _XL_PERCENT),
                ("VaR 95% (montant)", var95.get("var_amount", 0), _XL_MONEY),
                ("", "", None),
                ("Indice HHI", conc.get("hhi", 0), "0"),
                ("Concentration", conc.get("interpretation", ""), None),
                ("Actif dominant", conc.get("top_asset", ""), None),
                ("Poids actif dominant", (conc.get("top_concentration", 0) or 0) / 100, _XL_PERCENT),
                ("", "", None),
                ("Stress Test -20% (perte)", st20.get("potential_loss", 0), _XL_MONEY),
                ("Stress Test -20% (valeur)", st20.get("stressed_value", 0), _XL_MONEY),
                ("Stress Test -40% (perte)", st40.get("potential_loss", 0), _XL_MONEY),
                ("Stress Test -40% (valeur)", st40.get("stressed_value", 0), _XL_MONEY),
            ]
            for i, (label, value, fmt) in enumerate(risk_rows, start=2):
                ws_risk[f"A{i}"] = label
                ws_risk[f"A{i}"].border = _XL_BORDER
                if value != "":
                    ws_risk[f"B{i}"] = value
                ws_risk[f"B{i}"].border = _XL_BORDER
                if fmt:
                    ws_risk[f"B{i}"].number_format = fmt

            ws_risk.column_dimensions["A"].width = 28
            ws_risk.column_dimensions["B"].width = 18

        # ── Attribution sheet ──────────────────────────────────────────
        attr = data.get("attribution", {})
        if any(v > 0 for v in attr.values()):
            ws_attr = wb.create_sheet("Attribution")
            ws_attr["A1"] = "Attribution de Performance"
            ws_attr["A1"].font = Font(bold=True, size=14)

            attr_headers = ["Catégorie", "Valeur", "Poids"]
            for col, h in enumerate(attr_headers, 1):
                c = ws_attr.cell(row=3, column=col, value=h)
                c.font = _XL_HEADER_FONT
                c.fill = _XL_HEADER_FILL
                c.border = _XL_BORDER

            total_attr = sum(attr.values()) or 1
            attr_rows = [
                ("Alpha (Altcoins)", attr.get("alpha", 0)),
                ("Beta (BTC)", attr.get("beta", 0)),
                ("Protection (Or)", attr.get("protection", 0)),
                ("Munitions (Cash/Stables)", attr.get("munitions", 0)),
            ]
            for i, (label, value) in enumerate(attr_rows, 4):
                ws_attr.cell(row=i, column=1, value=label).border = _XL_BORDER
                c_val = ws_attr.cell(row=i, column=2, value=value)
                c_val.number_format = _XL_MONEY
                c_val.border = _XL_BORDER
                c_pct = ws_attr.cell(row=i, column=3, value=value / total_attr)
                c_pct.number_format = _XL_PERCENT
                c_pct.border = _XL_BORDER

            ws_attr.column_dimensions["A"].width = 28
            ws_attr.column_dimensions["B"].width = 16
            ws_attr.column_dimensions["C"].width = 12

        # ── Flux de Trésorerie sheet ──────────────────────────────────
        cf = data.get("cash_flows", {})
        if cf.get("total_deposits", 0) > 0 or cf.get("total_withdrawals", 0) > 0:
            ws_cf = wb.create_sheet("Flux de Trésorerie")
            ws_cf["A1"] = "Flux de Trésorerie (Cash Flows)"
            ws_cf["A1"].font = Font(bold=True, size=14)

            for cell_ref in ["A3", "B3"]:
                ws_cf[cell_ref].font = _XL_HEADER_FONT
                ws_cf[cell_ref].fill = _XL_HEADER_FILL
                ws_cf[cell_ref].border = _XL_BORDER
            ws_cf["A3"] = "Flux"
            ws_cf["B3"] = "Montant"

            cf_rows = [
                ("Total déposé", cf.get("total_deposits", 0)),
                ("Total retiré", cf.get("total_withdrawals", 0)),
                ("Flux nets (dépôts − retraits)", cf.get("net_flows", 0)),
                ("Plus/Moins-value réelle", summary.get("gain_loss", 0)),
            ]
            for i, (label, value) in enumerate(cf_rows, 4):
                ws_cf.cell(row=i, column=1, value=label).border = _XL_BORDER
                c = ws_cf.cell(row=i, column=2, value=value)
                c.number_format = _XL_MONEY
                c.border = _XL_BORDER

            ws_cf.column_dimensions["A"].width = 30
            ws_cf.column_dimensions["B"].width = 18

        # ── Performance par Plateforme sheet ─────────────────────────
        platforms = data.get("platform_analysis", [])
        if platforms:
            ws_plat = wb.create_sheet("Perf. par Plateforme")
            plat_headers = ["Plateforme", "Nb Actifs", "Valeur", "Investi", "Frais", "P&L Net", "ROI %"]
            for col, h in enumerate(plat_headers, 1):
                c = ws_plat.cell(row=1, column=col, value=h)
                c.font = _XL_HEADER_FONT
                c.fill = _XL_HEADER_FILL
                c.border = _XL_BORDER
            for row, p in enumerate(platforms, 2):
                vals = [
                    p["exchange"],
                    p["count"],
                    p["total_value"],
                    p["total_invested"],
                    p["total_fees"],
                    p["net_pnl"],
                    p["roi_percent"] / 100,
                ]
                for col, v in enumerate(vals, 1):
                    c = ws_plat.cell(row=row, column=col, value=v)
                    c.border = _XL_BORDER
                    if col in (3, 4, 5, 6):
                        c.number_format = _XL_MONEY
                    elif col == 7:
                        c.number_format = _XL_PERCENT
            for col in range(1, len(plat_headers) + 1):
                ws_plat.column_dimensions[get_column_letter(col)].width = 16

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()

    # ── Tax 2086 PDF ────────────────────────────────────────────────

    async def generate_tax_report_2086(
        self,
        db: AsyncSession,
        user_id: str,
        year: int,
    ) -> bytes:
        """Generate French tax report 2086 for crypto assets with real capital gains."""
        tax = await self.compute_tax_2086(db, user_id, year)

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("T", parent=styles["Heading1"], fontSize=20, spaceAfter=20, textColor=_BLUE)
        heading_style = ParagraphStyle(
            "H", parent=styles["Heading2"], fontSize=12, spaceBefore=15, spaceAfter=8, textColor=_DARK_BLUE
        )
        info_style = ParagraphStyle("I", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#64748b"))
        small_style = ParagraphStyle("S", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#64748b"))

        elements = []

        # ── Title ───────────────────────────────────────────────────
        elements.append(Paragraph(f"Déclaration Fiscale Crypto — Année {year}", title_style))
        elements.append(Paragraph("Formulaire 2086 — Plus-values sur actifs numériques", heading_style))
        elements.append(
            Paragraph(
                f"Document généré le {datetime.now().strftime('%d/%m/%Y')} — À usage indicatif uniquement", info_style
            )
        )
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

        t = Table(summary_rows, colWidths=[10 * cm, 5 * cm])
        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), _BLUE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 1, _BORDER_COLOR),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            # Highlight net PV row
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ]
        if tax.net_plus_value >= 0:
            style_cmds.append(("TEXTCOLOR", (1, -1), (1, -1), _GREEN))
        else:
            style_cmds.append(("TEXTCOLOR", (1, -1), (1, -1), _RED))
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

        t = Table(tax_rows, colWidths=[8 * cm, 3 * cm, 4 * cm])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), _BLUE),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 1, _BORDER_COLOR),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fef3c7")),
                ]
            )
        )
        elements.append(t)

        if tax.net_plus_value <= 0:
            elements.append(Spacer(1, 5))
            elements.append(Paragraph("Aucune imposition : la plus-value nette est négative ou nulle.", info_style))

        elements.append(Spacer(1, 20))

        # ── 3. Détail des cessions ──────────────────────────────────
        if tax.events:
            elements.append(Paragraph("3. Détail des cessions", heading_style))
            elements.append(
                Paragraph(
                    "Calcul selon la formule 2086 : PV = Prix cession − (Coût acquisition global × Prix cession / Valeur portefeuille)",
                    small_style,
                )
            )
            elements.append(Spacer(1, 8))

            header = ["Date", "Actif", "Type", "Qté", "Prix cession", "Fraction acq.", "PV/MV", "Durée"]
            rows = [header]
            for e in sorted(tax.events, key=lambda x: x.date):
                type_label = "Conv." if e.event_type == "conversion_out" else "Vente"
                duration = "≥2 ans" if e.holding_period == "long_terme" else "<2 ans"
                rows.append(
                    [
                        e.date.strftime("%d/%m/%Y"),
                        e.symbol,
                        type_label,
                        f"{e.quantity:,.6f}",
                        _money(e.cession_price),
                        _money(e.acquisition_fraction),
                        _money(e.gain_loss),
                        duration,
                    ]
                )

            t = Table(rows, colWidths=[2 * cm, 1.6 * cm, 1.4 * cm, 2 * cm, 2.4 * cm, 2.4 * cm, 2.2 * cm, 1.6 * cm])
            style_cmds = [
                ("BACKGROUND", (0, 0), (-1, 0), _BLUE),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 1, _BORDER_COLOR),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _LIGHT_BG]),
            ]
            # Color gain/loss column
            for i, e in enumerate(sorted(tax.events, key=lambda x: x.date), 1):
                c = _GREEN if e.gain_loss >= 0 else _RED
                style_cmds.append(("TEXTCOLOR", (6, i), (6, i), c))
            t.setStyle(TableStyle(style_cmds))
            elements.append(t)
        else:
            elements.append(Paragraph("Aucune cession d'actifs numériques enregistrée pour cette année.", info_style))

        elements.append(Spacer(1, 30))

        # ── 4. Mentions légales ─────────────────────────────────────
        elements.append(Paragraph("Mentions importantes", heading_style))
        elements.append(
            Paragraph(
                "Ce document est fourni à titre indicatif uniquement et ne constitue pas un conseil fiscal. "
                "Veuillez consulter un professionnel pour votre déclaration officielle. "
                "Les plus-values sur actifs numériques sont soumises au prélèvement forfaitaire unique (PFU) de 30% "
                "(12,8% d'impôt sur le revenu + 17,2% de prélèvements sociaux) ou au barème progressif de l'impôt sur le revenu sur option. "
                "Le calcul utilise la méthode du Prix Moyen Pondéré (PMP) global du portefeuille conformément à l'article 150 VH bis du CGI. "
                "La valeur du portefeuille au moment de chaque cession est estimée à partir des données disponibles.",
                info_style,
            )
        )

        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()

    # ── Tax Excel ───────────────────────────────────────────────────

    async def generate_tax_excel(
        self,
        db: AsyncSession,
        user_id: str,
        year: int,
    ) -> bytes:
        """Generate Excel file for tax reporting with full 2086 calculations."""
        tax = await self.compute_tax_2086(db, user_id, year)

        wb = Workbook()

        # ── Résumé sheet ────────────────────────────────────────────
        ws = wb.active
        ws.title = f"Résumé {year}"

        ws["A1"] = f"Déclaration Fiscale Crypto — Année {year}"
        ws["A1"].font = Font(bold=True, size=14)
        ws["A2"] = f"Généré le {datetime.now().strftime('%d/%m/%Y')}"
        ws["A2"].font = Font(italic=True, color="666666")

        # Summary data
        ws["A4"] = "Résumé des cessions"
        ws["A4"].font = Font(bold=True, size=12)

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
            ws[f"A{i}"] = label
            ws[f"B{i}"] = value
            if fmt:
                ws[f"B{i}"].number_format = fmt

        # Tax estimation
        row = 5 + len(summary_items) + 1
        ws[f"A{row}"] = "Estimation fiscale (PFU 30%)"
        ws[f"A{row}"].font = Font(bold=True, size=12)

        tax_items = [
            ("Impôt sur le revenu (12,8%)", tax.ir_12_8),
            ("Prélèvements sociaux (17,2%)", tax.ps_17_2),
            ("Total Flat Tax (30%)", tax.flat_tax_30),
        ]
        for i, (label, value) in enumerate(tax_items, row + 1):
            ws[f"A{i}"] = label
            ws[f"B{i}"] = value
            ws[f"B{i}"].number_format = _XL_MONEY
            if label.startswith("Total"):
                ws[f"A{i}"].font = Font(bold=True)
                ws[f"B{i}"].font = Font(bold=True)

        ws.column_dimensions["A"].width = 35
        ws.column_dimensions["B"].width = 18

        # ── Cessions sheet ──────────────────────────────────────────
        ws2 = wb.create_sheet("Cessions")
        headers = [
            "Date",
            "Actif",
            "Type",
            "Quantité",
            "Prix unitaire",
            "Prix cession",
            "Valeur portefeuille",
            "Coût acquisition",
            "Fraction acq.",
            "PV/MV",
            "Durée",
        ]
        for col, h in enumerate(headers, 1):
            c = ws2.cell(row=1, column=col, value=h)
            c.font = _XL_HEADER_FONT
            c.fill = _XL_HEADER_FILL
            c.border = _XL_BORDER

        for row, e in enumerate(sorted(tax.events, key=lambda x: x.date), 2):
            type_label = "Conversion" if e.event_type == "conversion_out" else "Vente"
            duration = "≥ 2 ans" if e.holding_period == "long_terme" else "< 2 ans"
            vals = [
                e.date.strftime("%d/%m/%Y"),
                e.symbol,
                type_label,
                e.quantity,
                e.unit_price,
                e.cession_price,
                e.portfolio_value,
                e.total_acquisition_cost,
                e.acquisition_fraction,
                e.gain_loss,
                duration,
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

    # ── Transactions PDF (dedicated) ────────────────────────────────

    def generate_transactions_pdf(self, data: Dict[str, Any]) -> bytes:
        """Generate a dedicated PDF with all transactions."""
        transactions = data.get("transactions", [])

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=1.5 * cm,
            leftMargin=1.5 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("T", parent=styles["Heading1"], fontSize=20, spaceAfter=20, textColor=_BLUE)
        heading_style = ParagraphStyle(
            "H", parent=styles["Heading2"], fontSize=12, spaceBefore=15, spaceAfter=8, textColor=_DARK_BLUE
        )
        normal_style = styles["Normal"]
        elements = []

        elements.append(Paragraph("Historique des Transactions", title_style))
        year = data.get("year")
        period = f"Année {year}" if year else "Toutes les années"
        elements.append(Paragraph(f"{period} — Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}", normal_style))
        elements.append(Spacer(1, 15))

        # Summary
        elements.append(Paragraph("Résumé", heading_style))
        nb = len(transactions)
        total_volume = sum(t.total for t in transactions)
        total_fees = sum(t.fee for t in transactions)
        summary_rows = [
            ["Nombre de transactions", str(nb)],
            ["Volume total", _money(total_volume)],
            ["Total frais", _money(total_fees)],
        ]
        t = Table(summary_rows, colWidths=[8 * cm, 5 * cm])
        t.setStyle(
            TableStyle(
                [
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 1, _BORDER_COLOR),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("BACKGROUND", (0, 0), (-1, -1), _LIGHT_BG),
                ]
            )
        )
        elements.append(t)
        elements.append(Spacer(1, 15))

        # Transaction table
        if transactions:
            elements.append(Paragraph("Détail", heading_style))
            _TYPE_MAP = {
                "buy": "Achat",
                "sell": "Vente",
                "transfer_in": "Transfert ↓",
                "transfer_out": "Transfert ↑",
                "conversion_in": "Conv. ↓",
                "conversion_out": "Conv. ↑",
                "airdrop": "Airdrop",
                "staking_reward": "Reward",
                "fee": "Frais",
                "dividend": "Dividende",
                "interest": "Intérêt",
                "staking": "Staking",
                "unstaking": "Unstaking",
            }
            rows = [["Date", "Type", "Actif", "Quantité", "Prix Unitaire", "Valeur Totale", "Frais"]]
            for tx in transactions:
                rows.append(
                    [
                        tx.date.strftime("%d/%m/%Y") if tx.date else "",
                        _TYPE_MAP.get(tx.transaction_type, tx.transaction_type),
                        tx.symbol,
                        f"{tx.quantity:,.6f}",
                        _money(tx.price),
                        _money(tx.total),
                        _money(tx.fee),
                    ]
                )
            t = Table(rows, colWidths=[2.2 * cm, 2.2 * cm, 2 * cm, 2.4 * cm, 2.8 * cm, 2.8 * cm, 2 * cm])
            t.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), _BLUE),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ("GRID", (0, 0), (-1, -1), 1, _BORDER_COLOR),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _LIGHT_BG]),
                    ]
                )
            )
            elements.append(t)

        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()

    # ── Transactions Excel ───────────────────────────────────────────

    def generate_transactions_excel(self, data: Dict[str, Any]) -> bytes:
        """Generate an Excel file with full transaction history."""
        transactions = data.get("transactions", [])
        wb = Workbook()
        ws = wb.active
        ws.title = "Transactions"

        _TYPE_MAP = {
            "buy": "Achat",
            "sell": "Vente",
            "transfer_in": "Transfert entrant",
            "transfer_out": "Transfert sortant",
            "conversion_in": "Conversion entrante",
            "conversion_out": "Conversion sortante",
            "airdrop": "Airdrop",
            "staking_reward": "Reward",
            "fee": "Frais",
            "dividend": "Dividende",
            "interest": "Intérêt",
            "staking": "Staking",
            "unstaking": "Unstaking",
        }

        headers = ["Date", "Type", "Actif", "Quantité", "Prix Unitaire (EUR)", "Valeur Totale (EUR)", "Frais (EUR)"]
        for col, h in enumerate(headers, 1):
            c = ws.cell(row=1, column=col, value=h)
            c.font = _XL_HEADER_FONT
            c.fill = _XL_HEADER_FILL
            c.border = _XL_BORDER

        for row, tx in enumerate(transactions, 2):
            ws.cell(row=row, column=1, value=tx.date.strftime("%d/%m/%Y") if tx.date else "").border = _XL_BORDER
            ws.cell(
                row=row, column=2, value=_TYPE_MAP.get(tx.transaction_type, tx.transaction_type)
            ).border = _XL_BORDER
            ws.cell(row=row, column=3, value=tx.symbol).border = _XL_BORDER
            c = ws.cell(row=row, column=4, value=tx.quantity)
            c.number_format = "0.000000"
            c.border = _XL_BORDER
            ws.cell(row=row, column=5, value=tx.price).number_format = _XL_MONEY
            ws.cell(row=row, column=5).border = _XL_BORDER
            ws.cell(row=row, column=6, value=tx.total).number_format = _XL_MONEY
            ws.cell(row=row, column=6).border = _XL_BORDER
            ws.cell(row=row, column=7, value=tx.fee).number_format = _XL_MONEY
            ws.cell(row=row, column=7).border = _XL_BORDER

        for col in range(1, len(headers) + 1):
            ws.column_dimensions[get_column_letter(col)].width = 18

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()

    # ── Transactions CSV ─────────────────────────────────────────────

    def generate_transactions_csv(self, data: Dict[str, Any]) -> bytes:
        """Generate a CSV file with full transaction history."""
        import csv

        transactions = data.get("transactions", [])

        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";")
        writer.writerow(
            ["Date", "Type", "Actif", "Quantité", "Prix Unitaire (EUR)", "Valeur Totale (EUR)", "Frais (EUR)"]
        )

        for tx in transactions:
            writer.writerow(
                [
                    tx.date.strftime("%d/%m/%Y") if tx.date else "",
                    tx.transaction_type,
                    tx.symbol,
                    f"{tx.quantity:.6f}",
                    f"{tx.price:.2f}",
                    f"{tx.total:.2f}",
                    f"{tx.fee:.2f}",
                ]
            )

        return buffer.getvalue().encode("utf-8-sig")  # BOM for Excel compatibility


# Singleton
report_service = ReportService()
