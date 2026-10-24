from app.domains.predictions.alpha import AlphaMixin
from app.domains.predictions.anomalies import AnomaliesMixin
from app.domains.predictions.events import EventsMixin
from app.domains.predictions.portfolio import PortfolioMixin
from app.domains.predictions.sentiment import SentimentMixin
from app.domains.predictions.track_record import TrackRecordMixin


class PredictionService(
    PortfolioMixin,
    AnomaliesMixin,
    SentimentMixin,
    EventsMixin,
    TrackRecordMixin,
    AlphaMixin,
):
    pass


prediction_service = PredictionService()
