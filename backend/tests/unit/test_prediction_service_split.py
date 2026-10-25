"""Le service de prédictions est assemblé par mixins : chaque méthode publique doit rester atteignable.

Un mixin qui cesse d'être hérité ne casse pas à l'import mais à l'appel (AttributeError), d'où ce test.
"""

import pytest

from app.domains.predictions.service import PredictionService

PUBLIC_API = [
    "get_price_prediction",
    "detect_anomalies",
    "get_market_sentiment",
    "get_portfolio_predictions",
    "get_market_cycle",
    "estimate_top_bottom",
    "get_top_alpha_asset",
    "get_strategy_map",
    "get_what_if",
    "get_market_events",
    "get_track_record",
    "get_portfolio_backtest",
]


@pytest.mark.parametrize("method", PUBLIC_API)
def test_public_method_is_reachable(method: str) -> None:
    assert callable(getattr(PredictionService, method, None)), f"{method} n'est plus atteignable"
