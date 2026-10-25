import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.market_data.history.reader import local_series
from app.domains.portfolio.models import Asset
from app.domains.predictions.core import PredictionCore, held_assets, user_portfolio_ids
from app.domains.predictions.types import AnomalyDetection

logger = logging.getLogger(__name__)


class AnomaliesMixin(PredictionCore):
    async def _asset_anomaly(self, asset: Asset) -> AnomalyDetection | None:
        current_price = await self._get_current_price(asset.symbol, asset.asset_type)
        if current_price is None:
            return None
        prices = (await local_series(asset.symbol, 30)).prices
        anomaly = self.anomaly_detector.detect(
            symbol=asset.symbol,
            prices=prices if prices else [current_price],
            current_price=current_price,
            avg_buy_price=float(asset.avg_buy_price),
            asset_type=asset.asset_type.value,
        )
        if not anomaly:
            return None
        return AnomalyDetection(
            symbol=anomaly.symbol,
            is_anomaly=anomaly.is_anomaly,
            anomaly_type=anomaly.anomaly_type,
            severity=anomaly.severity,
            description=anomaly.description,
            detected_at=anomaly.detected_at,
            price_change_percent=anomaly.price_change_percent,
        )

    async def detect_anomalies(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> list[AnomalyDetection]:
        """Anomalies de cours sur 30 jours des actifs détenus (Isolation Forest, z-score) ; un actif en erreur
        est ignoré."""
        anomalies: list[AnomalyDetection] = []
        portfolio_ids = await user_portfolio_ids(db, user_id)
        if not portfolio_ids:
            return anomalies

        for asset in await held_assets(db, portfolio_ids):
            try:
                anomaly = await self._asset_anomaly(asset)
                if anomaly:
                    anomalies.append(anomaly)
            except Exception as e:  # noqa: BLE001
                logger.warning("Error checking anomaly for %s: %s", asset.symbol, e)
        return anomalies
