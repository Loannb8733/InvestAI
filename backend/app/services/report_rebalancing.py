"""Portfolio rebalancing: target-allocation orders, tax estimate, and PDF.

Extracted from report_service as a mixin. ReportService inherits
RebalancingReportMixin; report_service re-exports RebalanceOrder /
RebalancingReport for backwards compatibility.
"""

from __future__ import annotations

import io
import logging
from collections import defaultdict as _defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction
from app.services import fifo_replay
from app.services.metrics_service import metrics_service
from app.services.report_common import (
    _BLUE,
    _BORDER_COLOR,
    _DARK_BLUE,
    _GREEN,
    _LIGHT_BG,
    _RED,
    _ZERO,
    CRYPTO_ASSET_CLASSES,
    CRYPTO_CLASS_LABELS,
    _build_doc_with_footer,
    _format_paris_dt,
    _money,
    _pct,
)
from app.services.report_tax import TAX_MODE

logger = logging.getLogger(__name__)


@dataclass
class RebalanceOrder:
    """A single suggested buy or sell to reach target allocation."""

    category: str  # L1, L2, DeFi, Stable, Meme, Other
    action: str  # "buy" / "sell"
    amount_eur: float  # absolute EUR amount
    current_pct: float
    target_pct: float
    drift_pct: float  # current − target
    # Tax impact (sell orders only)
    estimated_gain: float = 0.0
    estimated_tax: float = 0.0  # PFU 30%


@dataclass
class RebalancingReport:
    """Full rebalancing report."""

    total_value: float
    categories: List[Dict[str, Any]]  # current allocation per category
    orders: List[RebalanceOrder]
    total_sell_amount: float = 0.0
    total_buy_amount: float = 0.0
    total_estimated_gain: float = 0.0
    total_estimated_tax: float = 0.0
    hhi_before: float = 0.0
    hhi_after: float = 0.0


class RebalancingReportMixin:
    """Mixed into ReportService — rebalancing orders + tax + PDF."""

    async def get_rebalancing_report(
        self,
        db: AsyncSession,
        user_id: str,
        target_allocations: Dict[str, float],
        currency: str = "EUR",
        estimate_tax: bool = True,
    ) -> RebalancingReport:
        """Compute rebalancing orders to reach target allocation per crypto class.

        Args:
            target_allocations: e.g. {"L1": 0.5, "Stable": 0.3, "DeFi": 0.2}
                Values must sum to 1.0 (100%).
            currency: Portfolio currency.

        Returns:
            RebalancingReport with current allocation, drift, suggested orders,
            and estimated tax impact (PFU 30%) for sell orders via FIFO.
        """
        # 1. Fetch portfolio data (single source of truth)
        dashboard = await metrics_service.get_user_dashboard_metrics(
            db,
            user_id,
            currency=currency,
        )
        total_value = dashboard.get("total_value", 0.0)

        if total_value <= 0:
            return RebalancingReport(
                total_value=0,
                categories=[],
                orders=[],
            )

        # 2. Group crypto assets by class
        allocations = dashboard.get("aggregated_assets", [])
        class_totals: Dict[str, float] = _defaultdict(float)
        class_assets: Dict[str, List[Dict[str, Any]]] = _defaultdict(list)

        for a in allocations:
            if a.get("asset_type") != "crypto":
                continue
            sym = a.get("symbol", "").upper()
            val = a.get("current_value", 0.0)
            if val < 0.10:  # dust filter
                continue
            cls = CRYPTO_ASSET_CLASSES.get(sym, "Other")
            class_totals[cls] += val
            class_assets[cls].append(a)

        crypto_total = sum(class_totals.values())
        if crypto_total <= 0:
            return RebalancingReport(
                total_value=total_value,
                categories=[],
                orders=[],
            )

        # 3. Build current allocation breakdown
        all_classes = set(list(target_allocations.keys()) + list(class_totals.keys()))
        categories: List[Dict[str, Any]] = []
        for cls in sorted(all_classes):
            current_val = class_totals.get(cls, 0.0)
            current_pct = (current_val / crypto_total * 100) if crypto_total > 0 else 0.0
            target_pct = target_allocations.get(cls, 0.0) * 100
            categories.append(
                {
                    "category": cls,
                    "label": CRYPTO_CLASS_LABELS.get(cls, cls),
                    "current_value": round(current_val, 2),
                    "current_pct": round(current_pct, 2),
                    "target_pct": round(target_pct, 2),
                    "drift_pct": round(current_pct - target_pct, 2),
                    "drift_eur": round(current_val - crypto_total * target_allocations.get(cls, 0.0), 2),
                }
            )

        # 4. Compute rebalancing orders
        orders: List[RebalanceOrder] = []
        for cat in categories:
            drift_eur = cat["drift_eur"]
            if abs(drift_eur) < 1.0:  # ignore tiny drifts
                continue
            action = "sell" if drift_eur > 0 else "buy"
            orders.append(
                RebalanceOrder(
                    category=cat["category"],
                    action=action,
                    amount_eur=round(abs(drift_eur), 2),
                    current_pct=cat["current_pct"],
                    target_pct=cat["target_pct"],
                    drift_pct=cat["drift_pct"],
                )
            )

        # 5. Estimate tax impact for sell orders via FIFO
        # We need the FIFO layers to estimate unrealized gains on the assets to sell
        # (skippable — le widget de drift du dashboard n'a pas besoin du replay FIFO)
        if estimate_tax and any(o.action == "sell" for o in orders):
            await self._estimate_rebalancing_tax(
                db,
                user_id,
                orders,
                class_assets,
                currency,
            )

        # 6. HHI (concentration index) before/after
        weights_before = [(v / crypto_total * 100) for v in class_totals.values()]
        hhi_before = sum(w**2 for w in weights_before)

        weights_after = [target_allocations.get(cls, 0.0) * 100 for cls in all_classes]
        hhi_after = sum(w**2 for w in weights_after)

        total_sell = sum(o.amount_eur for o in orders if o.action == "sell")
        total_buy = sum(o.amount_eur for o in orders if o.action == "buy")
        total_gain = sum(o.estimated_gain for o in orders)
        total_tax = sum(o.estimated_tax for o in orders)

        return RebalancingReport(
            total_value=round(total_value, 2),
            categories=categories,
            orders=orders,
            total_sell_amount=round(total_sell, 2),
            total_buy_amount=round(total_buy, 2),
            total_estimated_gain=round(total_gain, 2),
            total_estimated_tax=round(total_tax, 2),
            hhi_before=round(hhi_before, 1),
            hhi_after=round(hhi_after, 1),
        )

    async def _estimate_rebalancing_tax(
        self,
        db: AsyncSession,
        user_id: str,
        orders: List[RebalanceOrder],
        class_assets: Dict[str, List[Dict[str, Any]]],
        currency: str,
    ) -> None:
        """Estimate unrealized P&L and PFU tax for sell orders using FIFO layers.

        Mutates orders in-place to fill estimated_gain and estimated_tax.
        """
        # Get all portfolios + assets + transactions for FIFO replay
        result = await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))
        portfolios = result.scalars().all()
        portfolio_ids = [p.id for p in portfolios]
        if not portfolio_ids:
            return

        asset_result = await db.execute(
            select(Asset).where(
                Asset.portfolio_id.in_(portfolio_ids),
                Asset.asset_type == AssetType.CRYPTO,
            )
        )
        assets = asset_result.scalars().all()
        aid_to_symbol = {str(a.id): a.symbol.upper() for a in assets}
        crypto_ids = [a.id for a in assets]
        if not crypto_ids:
            return

        trans_result = await db.execute(
            select(Transaction).where(Transaction.asset_id.in_(crypto_ids)).order_by(Transaction.executed_at.asc())
        )
        all_txs = list(trans_result.scalars().all())

        # Build FIFO layers via the unified engine, using the converged tax
        # config (FX-correct prices, conversion matching, deterministic order).
        # This replaces the old inline replay that ignored conversion_rate and
        # used raw transaction-currency prices as the cost basis — so the
        # estimated gain/tax now match the 2086's cost basis for FX trades.
        fifo = fifo_replay.replay(
            fifo_replay.sort_transactions(all_txs),
            aid_to_symbol,
            TAX_MODE.config,
        ).fifo

        # Now estimate gains for each sell order
        for order in orders:
            if order.action != "sell":
                continue

            category = order.category
            sell_remaining = Decimal(str(order.amount_eur))
            estimated_gain = _ZERO

            # Get assets in this category sorted by value (sell largest first)
            assets_in_class = class_assets.get(category, [])
            assets_sorted = sorted(assets_in_class, key=lambda a: a.get("value", 0), reverse=True)

            for asset_info in assets_sorted:
                if sell_remaining <= 0:
                    break
                sym = asset_info.get("symbol", "").upper()
                current_price = Decimal(str(asset_info.get("current_price", 0)))
                if current_price <= 0:
                    continue

                # Find FIFO layers for this symbol (all exchanges)
                sym_layers: list = []
                for fkey, layers in fifo.items():
                    if fkey[0] == sym and not fkey[1].startswith("__transit__"):
                        sym_layers.extend(layers)

                # Estimate how much qty we'd sell
                asset_value = Decimal(str(asset_info.get("value", 0)))
                sell_from_this = min(sell_remaining, asset_value)
                qty_to_sell = sell_from_this / current_price if current_price > 0 else _ZERO

                # Walk FIFO layers to compute gain
                remaining = qty_to_sell
                for layer in sym_layers:
                    if remaining <= 0:
                        break
                    take = min(layer["qty"], remaining)
                    gain = take * (current_price - layer["unit_cost"])
                    estimated_gain += gain
                    remaining -= take

                sell_remaining -= sell_from_this

            order.estimated_gain = round(float(estimated_gain), 2)
            order.estimated_tax = round(max(0.0, float(estimated_gain)) * 0.30, 2)

    # ── Rebalancing PDF ───────────────────────────────────────────────

    def generate_rebalancing_pdf(self, report: RebalancingReport) -> bytes:
        """Generate a PDF rebalancing report."""
        buffer = io.BytesIO()
        doc = _build_doc_with_footer(
            buffer,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "T",
            parent=styles["Heading1"],
            fontSize=20,
            spaceAfter=20,
            textColor=_BLUE,
        )
        heading_style = ParagraphStyle(
            "H",
            parent=styles["Heading2"],
            fontSize=13,
            spaceBefore=15,
            spaceAfter=8,
            textColor=_DARK_BLUE,
        )
        normal_style = styles["Normal"]
        info_style = ParagraphStyle(
            "I",
            parent=styles["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#64748b"),
        )
        elements = []

        # Title
        elements.append(Paragraph("Rapport de Rééquilibrage", title_style))
        elements.append(
            Paragraph(
                f"Généré le {_format_paris_dt()}",
                normal_style,
            )
        )
        elements.append(Spacer(1, 15))

        # 1. Portfolio summary
        elements.append(Paragraph("1. Valeur du portefeuille crypto", heading_style))
        elements.append(
            Paragraph(
                f"Valeur totale : <b>{_money(report.total_value)}</b>",
                normal_style,
            )
        )
        elements.append(Spacer(1, 15))

        # 2. Current vs Target allocation table
        elements.append(Paragraph("2. Allocation Actuelle vs Cible", heading_style))
        rows = [["Catégorie", "Valeur", "Actuel %", "Cible %", "Écart %", "Écart EUR"]]
        for cat in report.categories:
            rows.append(
                [
                    CRYPTO_CLASS_LABELS.get(cat["category"], cat["category"]),
                    _money(cat["current_value"]),
                    _pct(cat["current_pct"]),
                    _pct(cat["target_pct"]),
                    _pct(cat["drift_pct"]),
                    _money(cat["drift_eur"]),
                ]
            )
        t = Table(rows, colWidths=[3.5 * cm, 3 * cm, 2 * cm, 2 * cm, 2 * cm, 3 * cm])
        style_cmds = [
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
        # Color drift column
        for i, cat in enumerate(report.categories, 1):
            c = _GREEN if abs(cat["drift_pct"]) < 3 else _RED
            style_cmds.append(("TEXTCOLOR", (4, i), (5, i), c))
        t.setStyle(TableStyle(style_cmds))
        elements.append(t)
        elements.append(Spacer(1, 20))

        # 3. Suggested orders
        if report.orders:
            elements.append(Paragraph("3. Ordres de Rééquilibrage Suggérés", heading_style))
            order_rows = [["Action", "Catégorie", "Montant", "PV Latente", "Impôt (PFU 30%)"]]
            for o in report.orders:
                action_label = "VENDRE" if o.action == "sell" else "ACHETER"
                order_rows.append(
                    [
                        action_label,
                        CRYPTO_CLASS_LABELS.get(o.category, o.category),
                        _money(o.amount_eur),
                        _money(o.estimated_gain) if o.action == "sell" else "—",
                        _money(o.estimated_tax) if o.action == "sell" else "—",
                    ]
                )
            t = Table(order_rows, colWidths=[2.5 * cm, 3.5 * cm, 3 * cm, 3 * cm, 3.5 * cm])
            order_style = [
                ("BACKGROUND", (0, 0), (-1, 0), _BLUE),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 1, _BORDER_COLOR),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _LIGHT_BG]),
            ]
            for i, o in enumerate(report.orders, 1):
                c = _RED if o.action == "sell" else _GREEN
                order_style.append(("TEXTCOLOR", (0, i), (0, i), c))
            t.setStyle(TableStyle(order_style))
            elements.append(t)
            elements.append(Spacer(1, 15))

            # Tax summary
            elements.append(Paragraph("4. Impact Fiscal du Rééquilibrage", heading_style))
            tax_rows = [
                ["Total ventes", _money(report.total_sell_amount)],
                ["Total achats", _money(report.total_buy_amount)],
                ["Plus-value latente estimée", _money(report.total_estimated_gain)],
                ["Impôt estimé (PFU 30%)", _money(report.total_estimated_tax)],
            ]
            t = Table(tax_rows, colWidths=[8 * cm, 5 * cm])
            t.setStyle(
                TableStyle(
                    [
                        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                        ("FONTSIZE", (0, 0), (-1, -1), 10),
                        ("GRID", (0, 0), (-1, -1), 1, _BORDER_COLOR),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                        ("BACKGROUND", (0, 0), (-1, -1), _LIGHT_BG),
                        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                        ("TEXTCOLOR", (1, -1), (1, -1), _RED),
                    ]
                )
            )
            elements.append(t)
            elements.append(Spacer(1, 15))

        # 5. Concentration index
        elements.append(Paragraph("5. Score de Diversification (HHI)", heading_style))
        hhi_rows = [
            ["HHI avant rééquilibrage", f"{report.hhi_before:.0f}"],
            ["HHI après rééquilibrage", f"{report.hhi_after:.0f}"],
        ]
        t = Table(hhi_rows, colWidths=[8 * cm, 5 * cm])
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
        elements.append(Spacer(1, 10))
        elements.append(
            Paragraph(
                "HHI &lt; 1500 = bien diversifié | 1500-2500 = modéré | &gt; 2500 = concentré",
                info_style,
            )
        )
        elements.append(Spacer(1, 20))

        # Disclaimer
        elements.append(
            Paragraph(
                "Ce rapport est fourni à titre indicatif. L'estimation fiscale utilise "
                "les couches FIFO actuelles et le PFU à 30%. Consultez un professionnel "
                "avant d'exécuter les ordres suggérés.",
                info_style,
            )
        )

        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()
