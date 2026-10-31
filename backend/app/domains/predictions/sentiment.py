import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.market_data.fear_greed import fetch_fear_greed_index
from app.domains.market_data.prices.service import price_feed
from app.domains.portfolio.models import Asset, AssetType
from app.domains.predictions.core import PredictionCore, held_assets, user_portfolio_ids
from app.domains.predictions.types import MarketSentiment

logger = logging.getLogger(__name__)

SIGNIFICANT_MOVE_PCT = 1.0


@dataclass
class _Tally:
    crypto_count: int = 0
    stock_count: int = 0
    bullish_count: int = 0
    bearish_count: int = 0
    total_change: float = 0.0
    asset_count: int = 0

    def add(self, change_pct: float) -> None:
        self.total_change += change_pct
        self.asset_count += 1
        if change_pct > SIGNIFICANT_MOVE_PCT:
            self.bullish_count += 1
        elif change_pct < -SIGNIFICANT_MOVE_PCT:
            self.bearish_count += 1


def _split_symbols(assets: Sequence[Asset], tally: _Tally) -> tuple[list[str], list[tuple[str, str]]]:
    crypto_symbols: list[str] = []
    stock_symbols: list[tuple[str, str]] = []
    for asset in assets[:15]:
        if asset.asset_type == AssetType.CRYPTO:
            tally.crypto_count += 1
            crypto_symbols.append(asset.symbol)
        elif asset.asset_type in [AssetType.STOCK, AssetType.ETF]:
            tally.stock_count += 1
            stock_symbols.append((asset.symbol, asset.asset_type.value))
    return crypto_symbols, stock_symbols


async def _tally_crypto(crypto_symbols: list[str], tally: _Tally) -> None:
    if not crypto_symbols:
        return
    try:
        crypto_quotes = await price_feed.crypto(crypto_symbols)
        for quote in crypto_quotes.values():
            tally.add(quote.change_percent_24h)
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to fetch batch crypto prices for sentiment: %s", e)


async def _tally_stocks(stock_symbols: list[tuple[str, str]], tally: _Tally) -> None:
    for sym, atype in stock_symbols:
        try:
            stock_quote = await price_feed.quote(sym, atype)
            if stock_quote is not None:
                tally.add(stock_quote.change_percent_24h)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Sentiment price fetch failed for %s: %s", sym, exc)


async def _portfolio_tally(db: AsyncSession, user_id: str) -> _Tally:
    tally = _Tally()
    portfolio_ids = await user_portfolio_ids(db, user_id)
    if portfolio_ids:
        crypto_symbols, stock_symbols = _split_symbols(await held_assets(db, portfolio_ids), tally)
        await _tally_crypto(crypto_symbols, tally)
        await _tally_stocks(stock_symbols, tally)
    return tally


def _fallback_fear_greed(tally: _Tally) -> int:
    if tally.asset_count > 0:
        avg_change = tally.total_change / tally.asset_count
        return int(max(0, min(100, 50 + avg_change * 10)))
    return 50


def _phase(fear_greed: int) -> tuple[str, str]:
    if fear_greed >= 60:
        return "bullish", "markup"
    if fear_greed <= 40:
        return "bearish", "markdown"
    return "neutral", "accumulation" if fear_greed > 50 else "distribution"


def _signals(fear_greed: int, tally: _Tally) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    if fear_greed > 75:
        signals.append(
            {
                "type": "warning",
                "message": "Marché en zone de cupidité extrême",
                "action": "Envisagez de prendre des profits",
            }
        )
    elif fear_greed < 25:
        signals.append(
            {
                "type": "opportunity",
                "message": "Marché en zone de peur extrême",
                "action": "Opportunité d'achat potentielle",
            }
        )
    if tally.bullish_count > 0:
        signals.append(
            {
                "type": "buy",
                "message": f"{tally.bullish_count} actif(s) en hausse significative (+1%)",
                "action": "Momentum positif sur votre portefeuille",
            }
        )
    if tally.bearish_count > 0:
        signals.append(
            {
                "type": "sell",
                "message": f"{tally.bearish_count} actif(s) en baisse significative (-1%)",
                "action": "Surveillez vos positions en baisse",
            }
        )
    return signals


def _concentration_signal(tally: _Tally) -> dict[str, Any] | None:
    crypto_count = tally.crypto_count
    total_assets = crypto_count + tally.stock_count
    if crypto_count > 0 and total_assets > 0 and crypto_count / total_assets > 0.8 and crypto_count >= 3:
        return {
            "type": "info",
            "message": f"Forte concentration crypto: {crypto_count}/{total_assets} actifs",
            "action": "Envisagez de diversifier avec d'autres classes d'actifs",
        }
    return None


class SentimentMixin(PredictionCore):
    async def get_market_sentiment(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> MarketSentiment:
        """Sentiment d'après l'indice Fear & Greed (à défaut la variation 24 h moyenne des 15 premiers actifs
        détenus), avec signaux de cupidité/peur extrême, de mouvements de plus de 1 % et de concentration crypto."""
        tally = await _portfolio_tally(db, user_id)
        fear_greed = await fetch_fear_greed_index()
        if fear_greed is None:
            fear_greed = _fallback_fear_greed(tally)

        sentiment, phase = _phase(fear_greed)
        signals = _signals(fear_greed, tally)
        concentration = _concentration_signal(tally)
        if concentration is not None:
            signals.append(concentration)

        return MarketSentiment(
            overall_sentiment=sentiment,
            sentiment_score=(fear_greed - 50) * 2,
            fear_greed_index=fear_greed,
            market_phase=phase,
            signals=signals,
        )
