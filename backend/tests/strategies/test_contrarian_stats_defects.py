from typing import Any

from app.domains.strategies.builders_buy import build_conviction_buy_strategy
from app.domains.strategies.suggestions import _accumulation_candidates

ASSETS = [{"symbol": "BTC", "alpha_score": 20}, {"symbol": "ETH", "alpha_score": 10}]


def _conviction(fear_greed: int) -> dict[str, Any] | None:
    return build_conviction_buy_strategy(ASSETS, ASSETS, "bearish", 0.5, fear_greed, 1000.0)


def test_conviction_buy_follows_the_backtested_threshold() -> None:
    assert _conviction(24) is not None
    assert _conviction(25) is None


def test_conviction_buy_fires_at_maximal_fear() -> None:
    assert _conviction(0) is not None


def test_accumulation_lowers_the_alpha_bar_at_maximal_fear() -> None:
    assert [a["symbol"] for a in _accumulation_candidates(ASSETS, 0)] == ["BTC"]
