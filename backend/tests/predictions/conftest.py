import pytest

from app.services.prediction_service import prediction_service
from tests.predictions.forecaster_double import DeterministicForecaster


@pytest.fixture
def deterministic_forecaster(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prediction_service, "forecaster", DeterministicForecaster())
