"""ML Prediction service for price forecasting and anomaly detection."""

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_cached_prediction, cache_prediction
from app.ml.anomaly_detector import AnomalyDetector
from app.ml.forecaster import PriceForecaster
from app.ml.historical_data import HistoricalDataFetcher
from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.services.price_service import PriceService

logger = logging.getLogger(__name__)


@dataclass
class PricePrediction:
    """Price prediction for an asset."""

    symbol: str
    current_price: float
    predictions: List[Dict]  # [{date, price, confidence_low, confidence_high}]
    trend: str  # "bullish", "bearish", "neutral"
    trend_strength: float  # 0-100
    support_level: float
    resistance_level: float
    recommendation: str
    model_used: str
    models_detail: List[Dict] = None  # [{name, weight_pct, mape, trend}]
    explanations: List[Dict] = None  # SHAP explanations from XGBoost
    _history_dates: List = None  # internal: cached for accuracy calc
    _history_prices: List[float] = None  # internal: cached for accuracy calc


@dataclass
class AnomalyDetection:
    """Anomaly detection result."""

    symbol: str
    is_anomaly: bool
    anomaly_type: Optional[str]
    severity: str
    description: str
    detected_at: datetime
    price_change_percent: float


@dataclass
class MarketSentiment:
    """Market sentiment analysis."""

    overall_sentiment: str
    sentiment_score: float
    fear_greed_index: int
    market_phase: str
    signals: List[Dict]


class PredictionService:
    """Service for ML-based predictions and analysis."""

    def __init__(self):
        self.price_service = PriceService()
        self.forecaster = PriceForecaster()
        self.anomaly_detector = AnomalyDetector()
        self.data_fetcher = HistoricalDataFetcher(
            coingecko_api_key=getattr(self.price_service, 'coingecko_api_key', None)
        )

    async def get_price_prediction(
        self,
        symbol: str,
        asset_type: AssetType,
        days_ahead: int = 7,
    ) -> PricePrediction:
        """Generate price predictions using ML models."""
        # Check cache first
        cached = await get_cached_prediction(symbol, days_ahead)
        if cached:
            return PricePrediction(**{k: v for k, v in cached.items() if not k.startswith('_')})

        current_price = await self._get_current_price(symbol, asset_type)

        if current_price == 0:
            return self._empty_prediction(symbol)

        # Fetch historical data (90 days for Prophet, less is OK for linear)
        dates, prices = await self.data_fetcher.get_history(
            symbol, asset_type.value, days=90
        )

        # Use enough decimal places for micro-price assets (PEPE, SHIB, etc.)
        def smart_round(v: float) -> float:
            if v == 0:
                return 0.0
            if abs(v) < 0.01:
                return round(v, 10)
            return round(v, 2)

        if prices and len(prices) >= 5:
            # Use ML forecaster
            result = self.forecaster.ensemble_forecast(prices, dates, days_ahead)

            predictions = [
                {
                    "date": result.dates[i],
                    "price": smart_round(result.prices[i]),
                    "confidence_low": smart_round(result.confidence_low[i]),
                    "confidence_high": smart_round(result.confidence_high[i]),
                }
                for i in range(len(result.dates))
            ]

            trend = result.trend
            trend_strength = result.trend_strength
            model_used = result.model_used
            models_detail = result.models_detail
            explanations = getattr(result, 'explanations', [])
        else:
            # Fallback: simple random walk when no historical data
            logger.warning("No historical data for %s, using random walk", symbol)
            predictions, trend, trend_strength = await self._random_walk_fallback(
                symbol, current_price, asset_type, days_ahead
            )
            model_used = "random_walk"
            models_detail = []
            explanations = []

        # Support/resistance from pivot points + price level clustering
        if prices and len(prices) >= 10:
            support, resistance = self._compute_support_resistance(
                prices, current_price
            )
        else:
            vol = await self._get_daily_volatility(symbol, asset_type)
            support = current_price * (1 - vol * 5)
            resistance = current_price * (1 + vol * 5)

        recommendation = self._generate_recommendation(
            trend, trend_strength, current_price, support, resistance
        )

        # Log prediction for monitoring
        try:
            from app.models.prediction_log import PredictionLog
            from app.core.database import AsyncSessionLocal

            if predictions:
                last_pred = predictions[-1]
                log_entry = PredictionLog(
                    symbol=symbol,
                    asset_type=asset_type.value,
                    model_used=model_used,
                    predicted_price=float(last_pred["price"]),
                    target_date=datetime.strptime(last_pred["date"], "%Y-%m-%d"),
                    horizon_days=days_ahead,
                    models_detail=models_detail,
                )
                async with AsyncSessionLocal() as log_db:
                    log_db.add(log_entry)
                    await log_db.commit()
        except Exception as e:
            logger.debug("Failed to log prediction: %s", e)

        # Cache the result
        result_dict = {
            "symbol": symbol,
            "current_price": current_price,
            "predictions": predictions,
            "trend": trend,
            "trend_strength": round(trend_strength, 1),
            "support_level": smart_round(support),
            "resistance_level": smart_round(resistance),
            "recommendation": recommendation,
            "model_used": model_used,
            "models_detail": models_detail or [],
        }
        await cache_prediction(symbol, days_ahead, result_dict)

        return PricePrediction(
            symbol=symbol,
            current_price=current_price,
            predictions=predictions,
            trend=trend,
            trend_strength=round(trend_strength, 1),
            support_level=smart_round(support),
            resistance_level=smart_round(resistance),
            recommendation=recommendation,
            model_used=model_used,
            models_detail=models_detail or [],
            explanations=explanations or [],
            _history_dates=dates,
            _history_prices=prices,
        )

    async def detect_anomalies(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> List[AnomalyDetection]:
        """Detect anomalies using Isolation Forest and Z-score."""
        anomalies = []

        result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == user_id,
            )
        )
        portfolios = result.scalars().all()
        portfolio_ids = [p.id for p in portfolios]

        if not portfolio_ids:
            return anomalies

        result = await db.execute(
            select(Asset).where(
                Asset.portfolio_id.in_(portfolio_ids),
                Asset.quantity > 0,
            )
        )
        assets = result.scalars().all()

        for asset in assets:
            try:
                current_price = await self._get_current_price(asset.symbol, asset.asset_type)
                if current_price == 0:
                    continue

                # Fetch historical prices for ML-based detection
                _, prices = await self.data_fetcher.get_history(
                    asset.symbol, asset.asset_type.value, days=30
                )

                anomaly = self.anomaly_detector.detect(
                    symbol=asset.symbol,
                    prices=prices if prices else [current_price],
                    current_price=current_price,
                    avg_buy_price=float(asset.avg_buy_price),
                    asset_type=asset.asset_type.value,
                )

                if anomaly:
                    anomalies.append(AnomalyDetection(
                        symbol=anomaly.symbol,
                        is_anomaly=anomaly.is_anomaly,
                        anomaly_type=anomaly.anomaly_type,
                        severity=anomaly.severity,
                        description=anomaly.description,
                        detected_at=anomaly.detected_at,
                        price_change_percent=anomaly.price_change_percent,
                    ))

            except Exception as e:
                logger.warning("Error checking anomaly for %s: %s", asset.symbol, e)

        return anomalies

    async def get_market_sentiment(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> MarketSentiment:
        """Analyze market sentiment based on real price data."""
        result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == user_id,
            )
        )
        portfolios = result.scalars().all()
        portfolio_ids = [p.id for p in portfolios]

        crypto_count = 0
        stock_count = 0
        bullish_count = 0
        bearish_count = 0
        total_change = 0.0
        asset_count = 0

        if portfolio_ids:
            result = await db.execute(
                select(Asset).where(
                    Asset.portfolio_id.in_(portfolio_ids),
                        Asset.quantity > 0,
                )
            )
            assets = result.scalars().all()

            # Separate crypto and stock/ETF symbols
            crypto_symbols = []
            stock_symbols = []
            for asset in assets[:15]:
                if asset.asset_type == AssetType.CRYPTO:
                    crypto_count += 1
                    crypto_symbols.append(asset.symbol)
                elif asset.asset_type in [AssetType.STOCK, AssetType.ETF]:
                    stock_count += 1
                    stock_symbols.append((asset.symbol, asset.asset_type.value))

            # Batch fetch crypto prices (single API call)
            if crypto_symbols:
                try:
                    crypto_prices = await self.price_service.get_multiple_crypto_prices(
                        crypto_symbols
                    )
                    for sym, price_data in crypto_prices.items():
                        change_pct = float(price_data.get("change_percent_24h", 0))
                        total_change += change_pct
                        asset_count += 1
                        if change_pct > 1:
                            bullish_count += 1
                        elif change_pct < -1:
                            bearish_count += 1
                except Exception as e:
                    logger.warning("Failed to fetch batch crypto prices for sentiment: %s", e)

            # Fetch stock/ETF prices individually (usually fewer)
            for sym, atype in stock_symbols:
                try:
                    price_data = await self.price_service.get_price(sym, atype)
                    if price_data:
                        change_pct = float(price_data.get("change_percent_24h", 0))
                        total_change += change_pct
                        asset_count += 1
                        if change_pct > 1:
                            bullish_count += 1
                        elif change_pct < -1:
                            bearish_count += 1
                except Exception:
                    pass

        # Fetch real Fear & Greed Index from alternative.me
        fear_greed = 50
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get("https://api.alternative.me/fng/?limit=1")
                resp.raise_for_status()
                fng_data = resp.json()
                if fng_data.get("data"):
                    fear_greed = int(fng_data["data"][0].get("value", 50))
        except Exception as e:
            logger.warning("Failed to fetch Fear & Greed Index: %s", e)
            # Fallback: compute from portfolio data
            if asset_count > 0:
                avg_change = total_change / asset_count
                fear_greed = int(max(0, min(100, 50 + avg_change * 10)))

        if fear_greed >= 60:
            sentiment = "bullish"
            phase = "markup"
        elif fear_greed <= 40:
            sentiment = "bearish"
            phase = "markdown"
        else:
            sentiment = "neutral"
            phase = "accumulation" if fear_greed > 50 else "distribution"

        sentiment_score = (fear_greed - 50) * 2

        signals = []

        if fear_greed > 75:
            signals.append({
                "type": "warning",
                "message": "Marché en zone de cupidité extrême",
                "action": "Envisagez de prendre des profits",
            })
        elif fear_greed < 25:
            signals.append({
                "type": "opportunity",
                "message": "Marché en zone de peur extrême",
                "action": "Opportunité d'achat potentielle",
            })

        if bullish_count > 0:
            signals.append({
                "type": "buy",
                "message": f"{bullish_count} actif(s) en hausse significative (+1%)",
                "action": "Momentum positif sur votre portefeuille",
            })
        if bearish_count > 0:
            signals.append({
                "type": "sell",
                "message": f"{bearish_count} actif(s) en baisse significative (-1%)",
                "action": "Surveillez vos positions en baisse",
            })

        if crypto_count > 0:
            signals.append({
                "type": "info",
                "message": f"Exposition crypto: {crypto_count} actif(s)",
                "action": "Surveillez la volatilité du marché crypto",
            })

        return MarketSentiment(
            overall_sentiment=sentiment,
            sentiment_score=sentiment_score,
            fear_greed_index=fear_greed,
            market_phase=phase,
            signals=signals,
        )

    async def get_portfolio_predictions(
        self,
        db: AsyncSession,
        user_id: str,
        days_ahead: int = 7,
    ) -> Dict:
        """Get predictions for all assets in user's portfolio."""
        result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == user_id,
            )
        )
        portfolios = result.scalars().all()
        portfolio_ids = [p.id for p in portfolios]

        if not portfolio_ids:
            return {"predictions": [], "summary": {}}

        result = await db.execute(
            select(Asset).where(
                Asset.portfolio_id.in_(portfolio_ids),
                Asset.quantity > 0,
            )
        )
        raw_assets = result.scalars().all()

        # Deduplicate by symbol: aggregate quantities
        asset_map: Dict[str, object] = {}
        quantity_map: Dict[str, float] = {}
        for a in raw_assets:
            key = a.symbol
            if key not in asset_map:
                asset_map[key] = a
                quantity_map[key] = float(a.quantity)
            else:
                quantity_map[key] += float(a.quantity)
        assets = list(asset_map.values())

        predictions = []
        bullish_count = 0
        bearish_count = 0
        total_current = 0.0
        total_predicted = 0.0

        for asset in assets[:10]:
            # Skip stablecoins — their price is pegged, prediction is meaningless
            if PriceService.is_stablecoin(asset.symbol):
                continue

            prediction = await self.get_price_prediction(
                asset.symbol, asset.asset_type, days_ahead
            )

            qty = quantity_map[asset.symbol]
            current_value = prediction.current_price * qty
            predicted_value = (
                prediction.predictions[-1]["price"] * qty
                if prediction.predictions
                else current_value
            )

            total_current += current_value
            total_predicted += predicted_value

            if prediction.trend == "bullish":
                bullish_count += 1
            elif prediction.trend == "bearish":
                bearish_count += 1

            predicted_price = prediction.predictions[-1]["price"] if prediction.predictions else 0
            change_percent = (
                ((predicted_price - prediction.current_price) / prediction.current_price * 100)
                if prediction.current_price > 0
                else 0.0
            )

            # Compute accuracy from already-fetched historical data (no extra API call)
            accuracy = self._compute_accuracy_from_data(
                prediction._history_dates or [],
                prediction._history_prices or [],
            )

            # Compute consensus from model trends, weights, and volatility
            models_detail = prediction.models_detail or []
            if len(models_detail) >= 2:
                trends = [m.get("trend", "neutral") for m in models_detail]
                models_agree = len(set(trends)) == 1
                # Consensus = weighted agreement with the majority trend
                trend_weights = {}
                for m in models_detail:
                    t = m.get("trend", "neutral")
                    trend_weights[t] = trend_weights.get(t, 0) + m.get("weight_pct", 0)
                max_trend_weight = max(trend_weights.values()) if trend_weights else 50
                consensus_score = max(0, min(100, float(max_trend_weight)))

                # Penalize consensus by recent volatility: high vol → less reliable
                hist_prices = prediction._history_prices or []
                if len(hist_prices) >= 10:
                    recent_rets = [
                        (hist_prices[i] - hist_prices[i - 1]) / hist_prices[i - 1]
                        for i in range(max(1, len(hist_prices) - 10), len(hist_prices))
                        if hist_prices[i - 1] > 0
                    ]
                    vol = float(np.std(recent_rets)) if recent_rets else 0.0
                    # >5% daily vol → subtract up to 20 points
                    vol_penalty = min(20, vol * 200)
                    consensus_score = max(0, consensus_score - vol_penalty)
            else:
                consensus_score = 50.0
                models_agree = True

            predictions.append({
                "symbol": asset.symbol,
                "name": asset.name,
                "asset_type": asset.asset_type.value,
                "current_price": prediction.current_price,
                "predicted_price": predicted_price,
                "change_percent": round(change_percent, 2),
                "trend": prediction.trend,
                "trend_strength": prediction.trend_strength,
                "recommendation": prediction.recommendation,
                "model_used": prediction.model_used,
                "predictions": prediction.predictions,
                "support_level": prediction.support_level,
                "resistance_level": prediction.resistance_level,
                "accuracy": accuracy,
                "consensus_score": round(consensus_score, 1),
                "models_agree": models_agree,
                "models_detail": models_detail,
                "explanations": prediction.explanations or [],
            })

        portfolio_change = (
            ((total_predicted - total_current) / total_current * 100)
            if total_current > 0
            else 0
        )

        overall_sentiment = (
            "bullish" if bullish_count > bearish_count
            else "bearish" if bearish_count > bullish_count
            else "neutral"
        )

        return {
            "predictions": predictions,
            "summary": {
                "total_current_value": round(total_current, 2),
                "total_predicted_value": round(total_predicted, 2),
                "expected_change_percent": round(portfolio_change, 2),
                "overall_sentiment": overall_sentiment,
                "bullish_assets": bullish_count,
                "bearish_assets": bearish_count,
                "neutral_assets": len(predictions) - bullish_count - bearish_count,
                "days_ahead": days_ahead,
            },
        }

    async def get_what_if(
        self,
        db: AsyncSession,
        user_id: str,
        scenarios: List[Dict],
    ) -> Dict:
        """Simulate what-if scenarios on the portfolio."""
        result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == user_id,
            )
        )
        portfolios = result.scalars().all()
        portfolio_ids = [p.id for p in portfolios]

        if not portfolio_ids:
            return {"current_value": 0, "simulated_value": 0, "impact_percent": 0, "per_asset": []}

        result = await db.execute(
            select(Asset).where(
                Asset.portfolio_id.in_(portfolio_ids),
                Asset.quantity > 0,
            )
        )
        raw_assets = result.scalars().all()

        # Deduplicate by symbol
        wi_asset_map: Dict[str, object] = {}
        wi_qty_map: Dict[str, float] = {}
        for a in raw_assets:
            if a.symbol not in wi_asset_map:
                wi_asset_map[a.symbol] = a
                wi_qty_map[a.symbol] = float(a.quantity)
            else:
                wi_qty_map[a.symbol] += float(a.quantity)
        assets = list(wi_asset_map.values())

        # Build scenario map
        scenario_map = {s["symbol"].upper(): s["change_percent"] for s in scenarios}

        per_asset = []
        total_current = 0.0
        total_simulated = 0.0

        for asset in assets[:15]:
            price = await self._get_current_price(asset.symbol, asset.asset_type)
            current_val = price * wi_qty_map[asset.symbol]
            change = scenario_map.get(asset.symbol.upper(), 0.0)
            simulated_val = current_val * (1 + change / 100)

            total_current += current_val
            total_simulated += simulated_val

            per_asset.append({
                "symbol": asset.symbol,
                "name": asset.name,
                "current_value": round(current_val, 2),
                "simulated_value": round(simulated_val, 2),
                "change_percent": change,
                "impact": round(simulated_val - current_val, 2),
            })

        impact_pct = ((total_simulated - total_current) / total_current * 100) if total_current > 0 else 0

        return {
            "current_value": round(total_current, 2),
            "simulated_value": round(total_simulated, 2),
            "impact_percent": round(impact_pct, 2),
            "per_asset": per_asset,
        }

    async def get_market_events(self) -> List[Dict]:
        """Return upcoming market events from web scraping + Forex Factory API."""
        import re
        now = datetime.utcnow()
        current_year = now.year
        events = []

        # Month name mappings
        month_map = {
            "january": 1, "february": 2, "march": 3, "april": 4,
            "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12,
        }

        # 1. Fetch this week's economic events from Forex Factory (free, no key)
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
                )
                resp.raise_for_status()
                data = resp.json()

            for item in data:
                impact = item.get("impact", "")
                if impact not in ("High", "Medium"):
                    continue
                date_str = item.get("date", "")
                if not date_str:
                    continue
                try:
                    evt_date = datetime.fromisoformat(
                        date_str.replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                except (ValueError, TypeError):
                    continue
                if evt_date < now:
                    continue

                country = item.get("country", "")
                title = item.get("title", "Événement économique")
                forecast = item.get("forecast", "")
                previous = item.get("previous", "")
                desc_parts = []
                if country:
                    desc_parts.append(country)
                if previous:
                    desc_parts.append(f"Précédent: {previous}")
                if forecast:
                    desc_parts.append(f"Prévision: {forecast}")

                events.append({
                    "title": title,
                    "date": evt_date.strftime("%Y-%m-%d"),
                    "category": "macro",
                    "description": " — ".join(desc_parts) if desc_parts else title,
                    "impact": "high" if impact == "High" else "medium",
                    "days_until": (evt_date - now).days,
                })
        except Exception as e:
            logger.warning("Failed to fetch Forex Factory calendar: %s", e)

        # 2. Scrape FOMC meeting dates from Federal Reserve website
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
                )
                resp.raise_for_status()
                html = resp.text

            # Pattern matches "Month DD-DD" or "Month DD-DD*" in FOMC calendar
            # The page groups by year, find the current/next year sections
            for year in [current_year, current_year + 1]:
                # Find meeting date patterns like "January 27-28" or "March 17-18*"
                pattern = rf'({"|".join(month_map.keys())})\s+(\d{{1,2}})-(\d{{1,2}})\*?'
                year_section_match = re.search(
                    rf'class="[^"]*"[^>]*>\s*{year}\s*<',
                    html, re.IGNORECASE
                )
                if not year_section_match:
                    continue

                # Search from year header to next year header or end
                start = year_section_match.start()
                next_year = re.search(
                    rf'class="[^"]*"[^>]*>\s*{year + 1}\s*<',
                    html[start + 100:], re.IGNORECASE
                )
                end = start + 100 + next_year.start() if next_year else len(html)
                section = html[start:end]

                for match in re.finditer(pattern, section, re.IGNORECASE):
                    month_name = match.group(1).lower()
                    last_day = int(match.group(3))  # Decision day (2nd day)
                    month = month_map.get(month_name)
                    if not month:
                        continue
                    try:
                        evt_date = datetime(year, month, last_day)
                    except ValueError:
                        continue
                    if evt_date < now:
                        continue

                    events.append({
                        "title": "Réunion FOMC (Fed)",
                        "date": evt_date.strftime("%Y-%m-%d"),
                        "category": "macro",
                        "description": "Décision sur les taux d'intérêt américains",
                        "impact": "high",
                        "days_until": (evt_date - now).days,
                    })
        except Exception as e:
            logger.warning("Failed to scrape FOMC calendar: %s", e)

        # 3. Scrape ECB meeting dates
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(
                    "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"
                )
                resp.raise_for_status()
                html = resp.text

            # ECB calendar uses dates like "5 February", "19 March", etc.
            # Look for "Monetary policy" sections with dates
            # Pattern: day month year in various formats
            pattern = r'(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})'
            monetary_sections = re.split(r'(?i)monetary\s+polic', html)

            seen_ecb_dates = set()
            for section in monetary_sections[1:]:  # Skip text before first match
                # Find all dates in the next ~500 chars after "Monetary polic..."
                chunk = section[:800]
                for match in re.finditer(pattern, chunk, re.IGNORECASE):
                    day = int(match.group(1))
                    month_name = match.group(2).lower()
                    year = int(match.group(3))
                    month = month_map.get(month_name)
                    if not month or year < current_year:
                        continue
                    try:
                        evt_date = datetime(year, month, day)
                    except ValueError:
                        continue
                    if evt_date < now:
                        continue
                    date_key = evt_date.strftime("%Y-%m-%d")
                    if date_key in seen_ecb_dates:
                        continue
                    seen_ecb_dates.add(date_key)

                    events.append({
                        "title": "Réunion BCE",
                        "date": date_key,
                        "category": "macro",
                        "description": "Décision sur les taux d'intérêt européens",
                        "impact": "high",
                        "days_until": (evt_date - now).days,
                    })
        except Exception as e:
            logger.warning("Failed to scrape ECB calendar: %s", e)

        # 4. Fiscal events (quarterly — these are fixed by definition)
        for year in [current_year, current_year + 1]:
            for q, (m, d, label) in enumerate([
                (3, 31, "Q1"), (6, 30, "Q2"), (9, 30, "Q3"), (12, 31, "Q4"),
            ], 1):
                evt_date = datetime(year, m, d)
                if evt_date < now or (evt_date - now).days > 365:
                    continue
                events.append({
                    "title": f"Fin de trimestre {label}",
                    "date": evt_date.strftime("%Y-%m-%d"),
                    "category": "fiscal",
                    "description": f"Clôture {label} — rééquilibrages institutionnels",
                    "impact": "medium",
                    "days_until": (evt_date - now).days,
                })

        # 5. Crypto events — dynamically estimate next BTC halving from blockchain
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("https://blockchain.info/q/getblockcount")
                if resp.status_code == 200:
                    current_block = int(resp.text.strip())
                    # Halving every 210,000 blocks
                    halving_interval = 210_000
                    next_halving_block = ((current_block // halving_interval) + 1) * halving_interval
                    blocks_remaining = next_halving_block - current_block
                    # ~10 minutes per block on average
                    minutes_remaining = blocks_remaining * 10
                    est_halving_date = now + timedelta(minutes=minutes_remaining)
                    halving_number = next_halving_block // halving_interval
                    if (est_halving_date - now).days > 0:
                        events.append({
                            "title": f"Halving Bitcoin #{halving_number}",
                            "date": est_halving_date.strftime("%Y-%m-%d"),
                            "category": "crypto",
                            "description": f"Réduction de la récompense de minage — bloc {next_halving_block:,}",
                            "impact": "high",
                            "days_until": (est_halving_date - now).days,
                        })
        except Exception as e:
            logger.warning("Failed to fetch BTC block height: %s", e)

        # Deduplicate by (title, date)
        seen = set()
        unique = []
        for e in events:
            key = (e["title"], e["date"])
            if key not in seen:
                seen.add(key)
                unique.append(e)

        unique.sort(key=lambda x: x["days_until"])
        return unique[:15]

    @staticmethod
    def _compute_support_resistance(
        prices: List[float], current_price: float
    ) -> Tuple[float, float]:
        """Compute support/resistance using pivot points + price clustering.

        1. Classic pivot points (H, L, C of recent window)
        2. K-means clustering of local extrema to find key price levels
        3. Pick nearest support below and resistance above current price
        """
        recent = prices[-min(60, len(prices)):]
        arr = np.array(recent, dtype=float)

        # --- Pivot points ---
        high = float(np.max(arr))
        low = float(np.min(arr))
        close = float(arr[-1])
        pivot = (high + low + close) / 3
        s1 = 2 * pivot - high
        s2 = pivot - (high - low)
        r1 = 2 * pivot - low
        r2 = pivot + (high - low)

        # --- Local extrema detection ---
        levels = [s1, s2, r1, r2, pivot]
        # Find local minima and maxima (±2 neighbors)
        for i in range(2, len(arr) - 2):
            if arr[i] <= arr[i - 1] and arr[i] <= arr[i + 1] and arr[i] <= arr[i - 2] and arr[i] <= arr[i + 2]:
                levels.append(float(arr[i]))
            elif arr[i] >= arr[i - 1] and arr[i] >= arr[i + 1] and arr[i] >= arr[i - 2] and arr[i] >= arr[i + 2]:
                levels.append(float(arr[i]))

        # --- Cluster nearby levels (within 1.5% of each other) ---
        levels.sort()
        clusters: List[List[float]] = []
        for lv in levels:
            if clusters and abs(lv - np.mean(clusters[-1])) / max(np.mean(clusters[-1]), 1e-10) < 0.015:
                clusters[-1].append(lv)
            else:
                clusters.append([lv])

        # Use cluster centroids as key levels
        key_levels = [float(np.mean(c)) for c in clusters]

        # Find nearest support (below current) and resistance (above current)
        supports = [lv for lv in key_levels if lv < current_price]
        resistances = [lv for lv in key_levels if lv > current_price]

        support = max(supports) if supports else current_price * 0.95
        resistance = min(resistances) if resistances else current_price * 1.05

        return support, resistance

    def _compute_accuracy_from_data(
        self, dates: List, prices: List[float]
    ) -> float:
        """Compute prediction accuracy via ensemble backtesting on already-fetched data.

        Runs the full ensemble_forecast on multiple train/test splits and measures
        the actual MAPE against realized prices.
        """
        try:
            if not prices or len(prices) < 14:
                return 50.0

            errors = []
            n = len(prices)
            # Test on 3 different splits: predict last 7, 14, 21 days
            for split in [n - 7, n - 14, n - 21]:
                if split < 10:
                    continue
                train_prices = prices[:split]
                train_dates = dates[:split] if dates else None
                horizon = min(7, n - split)
                if horizon < 1:
                    continue

                # Use ensemble forecast instead of just linear
                try:
                    result = self.forecaster.ensemble_forecast(
                        train_prices, train_dates, horizon
                    )
                except Exception:
                    result = self.forecaster._linear_forecast(
                        train_prices, train_dates, horizon
                    )

                # Measure error at each predicted day
                for i in range(min(len(result.prices), horizon)):
                    actual = prices[split + i]
                    predicted = result.prices[i]
                    if actual > 0:
                        error = abs(predicted - actual) / actual * 100
                        errors.append(error)

            if not errors:
                return 50.0

            mape = sum(errors) / len(errors)

            # Penalize high recent volatility (less predictable)
            if len(prices) >= 10:
                recent_returns = [
                    (prices[i] - prices[i - 1]) / prices[i - 1]
                    for i in range(max(1, len(prices) - 10), len(prices))
                    if prices[i - 1] > 0
                ]
                vol = float(np.std(recent_returns)) if recent_returns else 0.0
                # High vol (>5% daily) → reduce accuracy score
                vol_penalty = min(15, vol * 100)
            else:
                vol_penalty = 0.0

            accuracy = max(0, min(100, 100 - mape - vol_penalty))
            return round(accuracy, 1)
        except Exception as e:
            logger.warning("Accuracy computation failed: %s", e)
            return 50.0

    # -- Private helpers --

    async def _get_current_price(self, symbol: str, asset_type: AssetType) -> float:
        """Get current price for an asset."""
        try:
            if asset_type == AssetType.CRYPTO:
                data = await self.price_service.get_crypto_price(symbol)
            elif asset_type in [AssetType.STOCK, AssetType.ETF]:
                data = await self.price_service.get_stock_price(symbol)
            else:
                return 0.0

            if data and "price" in data:
                return float(data["price"])
            return 0.0
        except Exception:
            return 0.0

    async def _get_daily_volatility(self, symbol: str, asset_type: AssetType) -> float:
        """Compute daily volatility from actual historical data."""
        try:
            _, prices = await self.data_fetcher.get_history(
                symbol, asset_type.value, days=30
            )
            if prices and len(prices) >= 5:
                returns = [
                    (prices[i] - prices[i - 1]) / prices[i - 1]
                    for i in range(1, len(prices))
                    if prices[i - 1] > 0
                ]
                if returns:
                    return float(np.std(returns))
        except Exception:
            pass
        # Fallback only if data unavailable
        fallback = {
            AssetType.CRYPTO: 0.05,
            AssetType.STOCK: 0.015,
            AssetType.ETF: 0.01,
            AssetType.REAL_ESTATE: 0.002,
        }
        return fallback.get(asset_type, 0.02)

    def _generate_recommendation(
        self,
        trend: str,
        trend_strength: float,
        current_price: float,
        support: float,
        resistance: float,
    ) -> str:
        """Generate trading recommendation in French."""
        if trend == "bullish" and trend_strength > 50:
            return "Tendance haussière forte - Maintenir ou renforcer la position"
        elif trend == "bullish":
            return "Tendance légèrement haussière - Maintenir la position"
        elif trend == "bearish" and trend_strength > 50:
            return "Tendance baissière forte - Envisager de réduire l'exposition"
        elif trend == "bearish":
            return "Tendance légèrement baissière - Surveiller les supports"
        else:
            return "Tendance neutre - Attendre un signal plus clair"

    async def _random_walk_fallback(
        self,
        symbol: str,
        current_price: float,
        asset_type: AssetType,
        days_ahead: int,
    ) -> Tuple[List[Dict], str, float]:
        """Fallback random walk when no historical data available."""
        daily_volatility = await self._get_daily_volatility(symbol, asset_type)
        trend_factor = np.random.uniform(-0.02, 0.02)
        trend = "bullish" if trend_factor > 0.005 else "bearish" if trend_factor < -0.005 else "neutral"
        trend_strength = abs(trend_factor) * 1000

        predictions = []
        base_price = current_price

        for day in range(1, days_ahead + 1):
            date = datetime.utcnow() + timedelta(days=day)
            daily_return = trend_factor + np.random.normal(0, daily_volatility)
            predicted_price = base_price * (1 + daily_return)
            confidence = daily_volatility * math.sqrt(day) * 1.96
            confidence_low = predicted_price * (1 - confidence)
            confidence_high = predicted_price * (1 + confidence)

            def _rw_round(v):
                if abs(v) < 0.01:
                    return round(v, 10)
                return round(v, 2)

            predictions.append({
                "date": date.strftime("%Y-%m-%d"),
                "price": _rw_round(predicted_price),
                "confidence_low": _rw_round(max(0, confidence_low)),
                "confidence_high": _rw_round(confidence_high),
            })
            base_price = predicted_price

        return predictions, trend, trend_strength

    def _empty_prediction(self, symbol: str) -> PricePrediction:
        """Return empty prediction."""
        return PricePrediction(
            symbol=symbol,
            current_price=0,
            predictions=[],
            trend="neutral",
            trend_strength=0,
            support_level=0,
            resistance_level=0,
            recommendation="Données insuffisantes pour générer une prédiction",
            model_used="none",
        )


# Singleton instance
prediction_service = PredictionService()
