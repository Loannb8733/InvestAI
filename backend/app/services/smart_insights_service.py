"""Smart Insights Service - AI-powered portfolio analysis and recommendations."""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.portfolio import Portfolio
from app.ml.historical_data import HistoricalDataFetcher
from app.ml.regime_detector import MarketRegimeDetector, MarketRegime, RegimeResult
from app.services.analytics_service import AnalyticsService
from app.services.prediction_service import PredictionService
from app.services.price_service import price_service
from app.tasks.history_cache import get_cached_history

logger = logging.getLogger(__name__)


class InsightSeverity(str, Enum):
    """Severity level for insights."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class InsightCategory(str, Enum):
    """Category of insight."""
    PERFORMANCE = "performance"
    RISK = "risk"
    DIVERSIFICATION = "diversification"
    REBALANCING = "rebalancing"
    ANOMALY = "anomaly"
    OPPORTUNITY = "opportunity"


@dataclass
class SmartInsight:
    """A single smart insight/recommendation."""
    category: InsightCategory
    severity: InsightSeverity
    title: str
    message: str
    metric_name: Optional[str] = None
    current_value: Optional[float] = None
    target_value: Optional[float] = None
    potential_improvement: Optional[str] = None
    actions: List[Dict] = field(default_factory=list)
    # Actions format: [{"type": "buy/sell/hold", "symbol": "BTC", "amount_eur": 500, "reason": "..."}]


@dataclass
class RebalancingOrder:
    """A suggested rebalancing order."""
    symbol: str
    name: str
    action: str  # "buy" or "sell"
    current_weight: float
    target_weight: float
    current_value_eur: float
    target_value_eur: float
    amount_eur: float  # Amount to buy (positive) or sell (negative)
    reason: str


@dataclass
class AnomalyImpact:
    """Anomaly with calculated EUR impact."""
    symbol: str
    anomaly_type: str
    severity: str
    description: str
    price_change_percent: float
    position_value_eur: float
    impact_eur: float  # Gain or loss in EUR
    detected_at: datetime


@dataclass
class PortfolioHealthReport:
    """Complete portfolio health analysis."""
    overall_score: int  # 0-100
    overall_status: str  # "excellent", "good", "fair", "poor", "critical"
    insights: List[SmartInsight]
    rebalancing_orders: List[RebalancingOrder]
    anomaly_impacts: List[AnomalyImpact]
    metrics_summary: Dict[str, float]
    market_regime: Optional[MarketRegime] = None
    generated_at: datetime = field(default_factory=datetime.utcnow)


class SmartInsightsService:
    """Service for generating smart portfolio insights and recommendations."""

    # Thresholds for health analysis
    SHARPE_EXCELLENT = 1.5
    SHARPE_GOOD = 1.0
    SHARPE_FAIR = 0.5
    SHARPE_POOR = 0.0

    CONCENTRATION_WARNING = 0.40  # 40% in single asset
    CONCENTRATION_CRITICAL = 0.60  # 60% in single asset

    VAR_WARNING = 0.10  # 10% daily VaR
    VAR_CRITICAL = 0.15  # 15% daily VaR

    VOLATILITY_HIGH = 0.50  # 50% annualized
    VOLATILITY_EXTREME = 0.80  # 80% annualized

    MIN_REBALANCE_THRESHOLD = 0.05  # 5% weight difference to suggest rebalancing

    @staticmethod
    def _safe(v) -> float:
        """Sanitize a numeric value: convert NaN/Inf/None to 0."""
        if v is None:
            return 0.0
        try:
            f = float(v)
            if math.isnan(f) or math.isinf(f):
                return 0.0
            return f
        except (TypeError, ValueError):
            return 0.0

    def __init__(self):
        self.analytics_service = AnalyticsService()
        self.prediction_service = PredictionService()
        self.regime_detector = MarketRegimeDetector()
        self.data_fetcher = HistoricalDataFetcher()

    async def get_portfolio_health(
        self,
        db: AsyncSession,
        user_id: str,
        days: int = 30,
    ) -> PortfolioHealthReport:
        """Generate complete portfolio health report with insights and recommendations."""
        insights: List[SmartInsight] = []

        # Get portfolio analytics
        try:
            analytics = await self.analytics_service.get_user_analytics(db, user_id, days)
        except Exception as e:
            logger.error(f"Failed to get analytics: {e}")
            return PortfolioHealthReport(
                overall_score=0,
                overall_status="unknown",
                insights=[SmartInsight(
                    category=InsightCategory.PERFORMANCE,
                    severity=InsightSeverity.WARNING,
                    title="Analyse impossible",
                    message="Impossible d'analyser le portfolio. Vérifiez que vous avez des actifs.",
                )],
                rebalancing_orders=[],
                anomaly_impacts=[],
                metrics_summary={},
                generated_at=datetime.utcnow(),
            )

        # Extract key metrics from PortfolioAnalytics dataclass (sanitize NaN/Inf)
        sharpe = self._safe(analytics.sharpe_ratio)
        sortino = self._safe(analytics.sortino_ratio)
        volatility = self._safe(analytics.portfolio_volatility)
        var_95 = self._safe(analytics.var_95)
        max_drawdown = self._safe(analytics.max_drawdown)
        total_value = self._safe(analytics.total_value)

        # Get diversification data
        try:
            diversification = await self.analytics_service.get_diversification_analysis(db, user_id)
            hhi = self._safe(diversification.get("concentration_risk", 0))
            # Build top_holdings from allocation_by_asset in analytics
            allocation_by_asset = analytics.allocation_by_asset or {}
            top_holdings = [
                {"symbol": symbol, "weight": self._safe(weight) / 100, "name": symbol}
                for symbol, weight in sorted(allocation_by_asset.items(), key=lambda x: -x[1])[:5]
            ]
        except Exception:
            hhi = 0.0
            top_holdings = []

        metrics_summary = {
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "volatility": volatility,
            "var_95": var_95,
            "max_drawdown": max_drawdown,
            "hhi": hhi,
            "total_value": total_value,
        }

        # === PERFORMANCE INSIGHTS ===
        insights.extend(self._analyze_sharpe(sharpe, sortino))

        # === RISK INSIGHTS ===
        insights.extend(self._analyze_risk(volatility, var_95, max_drawdown))

        # === DIVERSIFICATION INSIGHTS ===
        insights.extend(self._analyze_diversification(hhi, top_holdings))

        # === REBALANCING SUGGESTIONS ===
        rebalancing_orders = await self._get_rebalancing_suggestions(db, user_id, total_value)
        if rebalancing_orders:
            # Calculate potential Sharpe improvement
            insights.append(SmartInsight(
                category=InsightCategory.REBALANCING,
                severity=InsightSeverity.INFO,
                title="Optimisation possible",
                message=f"Un rééquilibrage de {len(rebalancing_orders)} positions pourrait améliorer votre ratio de Sharpe.",
                metric_name="positions_to_rebalance",
                current_value=len(rebalancing_orders),
                actions=[{
                    "type": order.action,
                    "symbol": order.symbol,
                    "amount_eur": order.amount_eur,
                    "reason": order.reason,
                } for order in rebalancing_orders[:3]],  # Top 3 actions
            ))

        # === ANOMALY IMPACTS ===
        anomaly_impacts = await self._get_anomaly_impacts(db, user_id)
        for impact in anomaly_impacts:
            severity = InsightSeverity.CRITICAL if impact.severity == "high" else InsightSeverity.WARNING
            insights.append(SmartInsight(
                category=InsightCategory.ANOMALY,
                severity=severity,
                title=f"Anomalie détectée sur {impact.symbol}",
                message=f"{impact.description}. Impact: {impact.impact_eur:+,.0f}€ ({impact.price_change_percent:+.1f}%)",
                metric_name="impact_eur",
                current_value=impact.impact_eur,
            ))

        # === MARKET REGIME ===
        market_regime = await self._get_market_regime(db, user_id, top_holdings, days)
        if market_regime and market_regime.market.dominant_regime != "unknown":
            regime_insight = self._regime_to_insight(market_regime.market)
            if regime_insight:
                insights.append(regime_insight)

        # Calculate overall score
        overall_score, overall_status = self._calculate_overall_score(
            sharpe, volatility, var_95, hhi, len(anomaly_impacts)
        )

        # Sort insights by severity
        severity_order = {InsightSeverity.CRITICAL: 0, InsightSeverity.WARNING: 1, InsightSeverity.INFO: 2}
        insights.sort(key=lambda x: severity_order.get(x.severity, 3))

        return PortfolioHealthReport(
            overall_score=overall_score,
            overall_status=overall_status,
            insights=insights,
            rebalancing_orders=rebalancing_orders,
            anomaly_impacts=anomaly_impacts,
            metrics_summary=metrics_summary,
            market_regime=market_regime,
            generated_at=datetime.utcnow(),
        )

    def _analyze_sharpe(self, sharpe: float, sortino: float) -> List[SmartInsight]:
        """Analyze Sharpe and Sortino ratios."""
        insights = []

        if sharpe < self.SHARPE_POOR:
            insights.append(SmartInsight(
                category=InsightCategory.PERFORMANCE,
                severity=InsightSeverity.CRITICAL,
                title="Performance très faible",
                message=f"Votre ratio de Sharpe ({sharpe:.2f}) est négatif. Votre portfolio sous-performe un placement sans risque.",
                metric_name="sharpe_ratio",
                current_value=sharpe,
                target_value=self.SHARPE_GOOD,
                potential_improvement="Diversifiez vers des actifs moins corrélés ou réduisez les positions perdantes.",
            ))
        elif sharpe < self.SHARPE_FAIR:
            insights.append(SmartInsight(
                category=InsightCategory.PERFORMANCE,
                severity=InsightSeverity.WARNING,
                title="Performance à améliorer",
                message=f"Votre ratio de Sharpe ({sharpe:.2f}) est faible. Le rendement ne compense pas suffisamment le risque pris.",
                metric_name="sharpe_ratio",
                current_value=sharpe,
                target_value=self.SHARPE_GOOD,
                potential_improvement=f"Ciblez un Sharpe > {self.SHARPE_GOOD} via une meilleure allocation.",
            ))
        elif sharpe < self.SHARPE_GOOD:
            insights.append(SmartInsight(
                category=InsightCategory.PERFORMANCE,
                severity=InsightSeverity.INFO,
                title="Performance correcte",
                message=f"Votre ratio de Sharpe ({sharpe:.2f}) est acceptable mais peut être optimisé.",
                metric_name="sharpe_ratio",
                current_value=sharpe,
                target_value=self.SHARPE_EXCELLENT,
            ))
        else:
            insights.append(SmartInsight(
                category=InsightCategory.PERFORMANCE,
                severity=InsightSeverity.INFO,
                title="Excellente performance",
                message=f"Votre ratio de Sharpe ({sharpe:.2f}) est excellent. Votre rendement ajusté au risque est très bon.",
                metric_name="sharpe_ratio",
                current_value=sharpe,
            ))

        return insights

    def _analyze_risk(self, volatility: float, var_95: float, max_drawdown: float) -> List[SmartInsight]:
        """Analyze risk metrics."""
        insights = []

        # Volatility analysis
        if volatility > self.VOLATILITY_EXTREME:
            insights.append(SmartInsight(
                category=InsightCategory.RISK,
                severity=InsightSeverity.CRITICAL,
                title="Volatilité extrême",
                message=f"Votre portfolio a une volatilité de {volatility*100:.0f}%. C'est très risqué.",
                metric_name="volatility",
                current_value=volatility,
                target_value=0.30,
                potential_improvement="Ajoutez des actifs stables (ETF obligataires, stablecoins) pour réduire la volatilité.",
            ))
        elif volatility > self.VOLATILITY_HIGH:
            insights.append(SmartInsight(
                category=InsightCategory.RISK,
                severity=InsightSeverity.WARNING,
                title="Volatilité élevée",
                message=f"Votre portfolio a une volatilité de {volatility*100:.0f}%. Préparez-vous à des variations importantes.",
                metric_name="volatility",
                current_value=volatility,
                target_value=0.30,
            ))

        # VaR analysis
        if var_95 > self.VAR_CRITICAL:
            insights.append(SmartInsight(
                category=InsightCategory.RISK,
                severity=InsightSeverity.CRITICAL,
                title="Risque de perte élevé",
                message=f"Votre VaR 95% est de {var_95*100:.1f}%. Vous pouvez perdre cette proportion en une journée (5% de chance).",
                metric_name="var_95",
                current_value=var_95,
                target_value=0.05,
            ))
        elif var_95 > self.VAR_WARNING:
            insights.append(SmartInsight(
                category=InsightCategory.RISK,
                severity=InsightSeverity.WARNING,
                title="VaR à surveiller",
                message=f"Votre VaR 95% est de {var_95*100:.1f}%. Le risque journalier est notable.",
                metric_name="var_95",
                current_value=var_95,
            ))

        # Max drawdown
        if max_drawdown > 0.30:
            insights.append(SmartInsight(
                category=InsightCategory.RISK,
                severity=InsightSeverity.WARNING,
                title="Drawdown important",
                message=f"Votre portfolio a subi une baisse max de {max_drawdown*100:.0f}% depuis son pic.",
                metric_name="max_drawdown",
                current_value=max_drawdown,
            ))

        return insights

    def _analyze_diversification(self, hhi: float, top_holdings: List[Dict]) -> List[SmartInsight]:
        """Analyze portfolio diversification."""
        insights = []

        # Check concentration in top holdings
        if top_holdings:
            top_weight = top_holdings[0].get("weight", 0) if top_holdings else 0
            top_symbol = top_holdings[0].get("symbol", "?") if top_holdings else "?"

            if top_weight > self.CONCENTRATION_CRITICAL:
                insights.append(SmartInsight(
                    category=InsightCategory.DIVERSIFICATION,
                    severity=InsightSeverity.CRITICAL,
                    title="Concentration excessive",
                    message=f"{top_symbol} représente {top_weight*100:.0f}% de votre portfolio. C'est trop concentré.",
                    metric_name="top_holding_weight",
                    current_value=top_weight,
                    target_value=0.25,
                    potential_improvement=f"Réduisez {top_symbol} à max 25% et diversifiez.",
                    actions=[{
                        "type": "sell",
                        "symbol": top_symbol,
                        "reason": "Réduire la concentration",
                    }],
                ))
            elif top_weight > self.CONCENTRATION_WARNING:
                insights.append(SmartInsight(
                    category=InsightCategory.DIVERSIFICATION,
                    severity=InsightSeverity.WARNING,
                    title="Concentration élevée",
                    message=f"{top_symbol} représente {top_weight*100:.0f}% de votre portfolio.",
                    metric_name="top_holding_weight",
                    current_value=top_weight,
                    target_value=0.25,
                ))

        # HHI analysis
        if hhi > 0.25:  # Concentrated
            insights.append(SmartInsight(
                category=InsightCategory.DIVERSIFICATION,
                severity=InsightSeverity.WARNING,
                title="Portfolio peu diversifié",
                message=f"Votre indice HHI ({hhi:.2f}) indique une concentration élevée.",
                metric_name="hhi",
                current_value=hhi,
                target_value=0.15,
                potential_improvement="Ajoutez des actifs décorrélés (actions, ETF, or).",
            ))
        elif hhi < 0.10:
            insights.append(SmartInsight(
                category=InsightCategory.DIVERSIFICATION,
                severity=InsightSeverity.INFO,
                title="Bonne diversification",
                message=f"Votre portfolio est bien diversifié (HHI: {hhi:.2f}).",
                metric_name="hhi",
                current_value=hhi,
            ))

        return insights

    async def _get_rebalancing_suggestions(
        self,
        db: AsyncSession,
        user_id: str,
        total_value: float,
    ) -> List[RebalancingOrder]:
        """Get concrete rebalancing orders based on MPT optimization."""
        if total_value <= 0:
            return []

        try:
            # Get optimal weights from MPT
            optimization = await self.analytics_service.optimize_portfolio(
                db, user_id, objective="max_sharpe"
            )
            if not optimization or not optimization.weights:
                return []

            # Weights from optimization are in percentage (0-100), convert to fraction
            optimal_weights = {sym: w / 100 for sym, w in optimization.weights.items()}

            # Get current allocation from analytics
            analytics = await self.analytics_service.get_user_analytics(db, user_id)
            allocation_by_asset = analytics.allocation_by_asset or {}
            # allocation_by_asset values are in percentage (0-100)
            current_holdings = {
                sym: {"symbol": sym, "weight": w / 100, "value": total_value * w / 100, "name": sym}
                for sym, w in allocation_by_asset.items()
            }

        except Exception as e:
            logger.error(f"Failed to get optimization: {e}")
            return []

        orders = []

        for symbol, target_weight in optimal_weights.items():
            current = current_holdings.get(symbol, {})
            current_weight = current.get("weight", 0)
            current_value = current.get("value", 0)
            name = current.get("name", symbol)

            weight_diff = target_weight - current_weight

            # Only suggest if difference is significant
            if abs(weight_diff) >= self.MIN_REBALANCE_THRESHOLD:
                target_value = total_value * target_weight
                amount = target_value - current_value
                action = "buy" if amount > 0 else "sell"

                reason = ""
                if action == "buy":
                    reason = f"Augmenter de {current_weight*100:.1f}% → {target_weight*100:.1f}% pour optimiser le Sharpe"
                else:
                    reason = f"Réduire de {current_weight*100:.1f}% → {target_weight*100:.1f}% (surpondéré)"

                orders.append(RebalancingOrder(
                    symbol=symbol,
                    name=name,
                    action=action,
                    current_weight=current_weight,
                    target_weight=target_weight,
                    current_value_eur=current_value,
                    target_value_eur=target_value,
                    amount_eur=abs(amount),
                    reason=reason,
                ))

        # Sort by absolute amount (biggest changes first)
        orders.sort(key=lambda x: x.amount_eur, reverse=True)

        return orders

    async def _get_anomaly_impacts(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> List[AnomalyImpact]:
        """Get anomalies with calculated EUR impact."""
        try:
            anomalies = await self.prediction_service.detect_anomalies(db, user_id)
        except Exception as e:
            logger.error(f"Failed to detect anomalies: {e}")
            return []

        impacts = []

        # Get user's assets to calculate position values
        portfolios_result = await db.execute(
            select(Portfolio).where(Portfolio.user_id == user_id)
        )
        portfolios = portfolios_result.scalars().all()

        # Build asset map
        asset_map = {}
        for portfolio in portfolios:
            assets_result = await db.execute(
                select(Asset).where(Asset.portfolio_id == portfolio.id)
            )
            for asset in assets_result.scalars().all():
                if asset.symbol not in asset_map:
                    asset_map[asset.symbol] = {
                        "quantity": float(asset.quantity),
                        "avg_buy_price": float(asset.avg_buy_price),
                    }
                else:
                    asset_map[asset.symbol]["quantity"] += float(asset.quantity)

        for anomaly in anomalies:
            if not anomaly.is_anomaly:
                continue

            symbol = anomaly.symbol
            asset_data = asset_map.get(symbol, {})
            quantity = asset_data.get("quantity", 0)

            # Get current price (prefer Redis cache to avoid CoinGecko rate limits)
            current_price = 0
            try:
                _, cached_prices = get_cached_history(symbol, days=7)
                if cached_prices:
                    current_price = cached_prices[-1]
                else:
                    current_price = await price_service.get_current_price(symbol, "crypto")
                    if not current_price:
                        current_price = await price_service.get_current_price(symbol, "stock")
            except Exception:
                current_price = asset_data.get("avg_buy_price", 0)

            position_value = quantity * (current_price or 0)
            price_change = anomaly.price_change_percent / 100

            # Calculate impact (how much was gained/lost due to this move)
            # If price dropped 15%, the impact is the value lost
            impact_eur = position_value * price_change

            impacts.append(AnomalyImpact(
                symbol=symbol,
                anomaly_type=anomaly.anomaly_type or "unknown",
                severity=anomaly.severity,
                description=anomaly.description,
                price_change_percent=anomaly.price_change_percent,
                position_value_eur=position_value,
                impact_eur=impact_eur,
                detected_at=anomaly.detected_at,
            ))

        # Sort by absolute impact
        impacts.sort(key=lambda x: abs(x.impact_eur), reverse=True)

        return impacts

    async def _get_market_regime(
        self,
        db: AsyncSession,
        user_id: str,
        top_holdings: List[Dict],
        days: int = 30,
    ) -> Optional[MarketRegime]:
        """Detect market regime for BTC (proxy) and top holdings."""
        # Minimum 90 jours pour que les indicateurs techniques fonctionnent (SMA50, Bollinger 20, etc.)
        regime_days = max(days, 90)
        try:
            # Fetch Fear & Greed Index
            fear_greed: Optional[int] = None
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get("https://api.alternative.me/fng/?limit=1")
                    if resp.status_code == 200:
                        fng_data = resp.json()
                        fear_greed = int(fng_data["data"][0].get("value", 50))
            except Exception as e:
                logger.warning("Failed to fetch Fear & Greed: %s", e)

            # Market regime via BTC as proxy (prefer Redis cache)
            _, btc_prices = get_cached_history("BTC", days=regime_days)
            if not btc_prices:
                try:
                    _, btc_prices = await self.data_fetcher.get_crypto_history("BTC", days=regime_days)
                except Exception:
                    btc_prices = []

            if len(btc_prices) < 7:
                return None

            market_result = self.regime_detector.detect(btc_prices, "BTC (Marche)", fear_greed)

            # Per-asset regime for top 5
            per_asset = []
            symbols_done = set()
            for holding in top_holdings[:5]:
                symbol = holding.get("symbol", "")
                if not symbol or symbol in symbols_done:
                    continue
                symbols_done.add(symbol)
                try:
                    _, prices = get_cached_history(symbol, days=regime_days)
                    if not prices:
                        _, prices = await self.data_fetcher.get_crypto_history(symbol, days=regime_days)
                    if len(prices) >= 7:
                        result = self.regime_detector.detect(prices, symbol, fear_greed)
                        per_asset.append(result)
                except Exception as e:
                    logger.debug("Could not fetch history for %s: %s", symbol, e)

            return MarketRegime(
                market=market_result,
                per_asset=per_asset,
            )

        except Exception as e:
            logger.error("Failed to detect market regime: %s", e)
            return None

    def _regime_to_insight(self, regime: RegimeResult) -> Optional[SmartInsight]:
        """Convert a regime result into an insight/recommendation."""
        dominant = regime.dominant_regime
        prob = regime.probabilities.get(dominant, 0)

        if prob < 0.30:
            return None  # Too uncertain

        messages = {
            "bearish": (
                InsightSeverity.WARNING,
                "Tendance baissiere detectee",
                f"Le marche semble baissier ({prob*100:.0f}% de probabilite). "
                f"Envisagez de securiser vos positions ou d'attendre un meilleur point d'entree.",
            ),
            "bottom": (
                InsightSeverity.INFO,
                "Creux potentiel detecte",
                f"Le marche montre des signes de creux ({prob*100:.0f}%). "
                f"Cela pourrait etre une zone d'accumulation si votre horizon est long terme.",
            ),
            "bullish": (
                InsightSeverity.INFO,
                "Marche haussier",
                f"Le marche est en tendance haussiere ({prob*100:.0f}%). "
                f"Conditions favorables pour vos positions.",
            ),
            "top": (
                InsightSeverity.WARNING,
                "Sommet potentiel detecte",
                f"Le marche montre des signes de surchauffe ({prob*100:.0f}%). "
                f"Envisagez de prendre des profits ou de renforcer vos stop-loss.",
            ),
        }

        if dominant not in messages:
            return None

        severity, title, message = messages[dominant]

        actions = []
        if dominant == "top":
            actions = [{"type": "sell", "symbol": "PORTFOLIO", "reason": "Prendre des profits partiels"}]
        elif dominant == "bottom":
            actions = [{"type": "buy", "symbol": "PORTFOLIO", "reason": "Zone d'accumulation potentielle"}]

        return SmartInsight(
            category=InsightCategory.OPPORTUNITY,
            severity=severity,
            title=title,
            message=message,
            metric_name="market_regime",
            current_value=prob,
            actions=actions,
        )

    def _calculate_overall_score(
        self,
        sharpe: float,
        volatility: float,
        var_95: float,
        hhi: float,
        anomaly_count: int,
    ) -> Tuple[int, str]:
        """Calculate overall portfolio health score (0-100)."""
        score = 100

        # Sharpe penalty/bonus (-30 to +10)
        if sharpe < 0:
            score -= 30
        elif sharpe < 0.5:
            score -= 20
        elif sharpe < 1.0:
            score -= 10
        elif sharpe > 1.5:
            score += 10

        # Volatility penalty (0 to -20)
        if volatility > 0.80:
            score -= 20
        elif volatility > 0.50:
            score -= 10

        # VaR penalty (0 to -15)
        if var_95 > 0.15:
            score -= 15
        elif var_95 > 0.10:
            score -= 10

        # Concentration penalty (0 to -15)
        if hhi > 0.40:
            score -= 15
        elif hhi > 0.25:
            score -= 10

        # Anomaly penalty (-5 per anomaly, max -20)
        score -= min(anomaly_count * 5, 20)

        # Clamp score
        score = max(0, min(100, score))

        # Determine status
        if score >= 80:
            status = "excellent"
        elif score >= 65:
            status = "good"
        elif score >= 50:
            status = "fair"
        elif score >= 30:
            status = "poor"
        else:
            status = "critical"

        return score, status


# Singleton instance
smart_insights_service = SmartInsightsService()
