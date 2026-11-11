import inspect
import json
import os
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import time_machine

from app.ml import adaptive_thresholds
from app.ml.anomaly_detector import AnomalyDetector
from app.ml.drift_detector import check_drift
from app.ml.forecaster import PriceForecaster
from app.ml.market_context import compute_market_context
from app.ml.regime_detector import MarketRegimeDetector
from tests.ml.series import SERIES, dates, with_spike

GOLDEN = Path(__file__).parent / "golden"
UPDATE = os.environ.get("GOLDEN_UPDATE") == "1"
NOW = datetime(2025, 9, 1, 12, 0, tzinfo=UTC)
CONTEXTS = [("bull", "crypto"), ("bear", "stock"), ("range", "etf"), ("calm", "real_estate")]

pytestmark = pytest.mark.usefixtures("empty_test_redis")


@pytest.fixture(autouse=True)
def _seeded_and_frozen() -> Any:
    np.random.seed(0)
    with time_machine.travel(NOW, tick=False):
        yield


def _plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _plain(asdict(value))
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    if isinstance(value, np.ndarray):
        return _plain(value.tolist())
    if isinstance(value, bool | np.bool_):
        return bool(value)
    if isinstance(value, float | np.floating):
        number = float(value)
        return number if not np.isfinite(number) else float(f"{number:.6g}")
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _check(name: str, observed: Any) -> None:
    path = GOLDEN / f"{name}.json"
    rendered = json.dumps(_plain(observed), indent=2, ensure_ascii=False, sort_keys=True, default=str) + "\n"
    if UPDATE or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
    assert path.read_text(encoding="utf-8") == rendered, f"golden {name} différent (GOLDEN_UPDATE=1)"


def _context(name: str, asset_type: str, fear_greed: int | None = 40) -> Any:
    return compute_market_context(SERIES[name], name.upper(), asset_type, fear_greed)


def test_market_context() -> None:
    observed = {f"{name}_{kind}": _context(name, kind) for name, kind in CONTEXTS}
    observed["short"] = compute_market_context(SERIES["bull"][:20], "SHORT", "crypto", None)
    _check("market_context", observed)


def _threshold_calls(ctx: Any) -> dict[str, Any]:
    regime_probs = {"bullish": 0.4, "bearish": 0.2, "top": 0.1, "bottom": 0.3}
    calls: dict[str, Any] = {
        "regime_adjustment_factor": [
            adaptive_thresholds.regime_adjustment_factor(ctx, regime, 0.7, change)
            for regime in ("bullish", "bearish", "top", "bottom")
            for change in (-12.0, 4.0)
        ],
        "ci_widening_factor": [
            adaptive_thresholds.ci_widening_factor(ctx, regime, conf)
            for regime in ("bullish", "bearish", "top", "bottom")
            for conf in (0.3, 0.8)
        ],
        "trend_significance_threshold": [adaptive_thresholds.trend_significance_threshold(ctx, h) for h in (7, 30, 90)],
        "trend_strength_scale": [adaptive_thresholds.trend_strength_scale(ctx, h) for h in (7, 30, 90)],
        "ci_floor": [adaptive_thresholds.ci_floor(ctx, h) for h in (7, 30, 90)],
        "cycle_position": [
            adaptive_thresholds.cycle_position(ctx),
            adaptive_thresholds.cycle_position(ctx, regime_probs),
        ],
    }
    for name, function in inspect.getmembers(adaptive_thresholds, inspect.isfunction):
        if name.startswith("_") or name in calls or function.__module__ != adaptive_thresholds.__name__:
            continue
        params = list(inspect.signature(function).parameters.values())
        if len(params) == 1 and "MarketContext" in str(params[0].annotation):
            calls[name] = function(ctx)
        elif not params:
            calls[name] = function()
    return calls


def test_adaptive_thresholds() -> None:
    observed = {f"{name}_{kind}": _threshold_calls(_context(name, kind)) for name, kind in CONTEXTS}
    observed["fear_greed_none"] = _threshold_calls(_context("bull", "crypto", None))
    observed["without_context"] = {
        "correlation_thresholds": adaptive_thresholds.correlation_thresholds(),
        "volatility_warning_thresholds": adaptive_thresholds.volatility_warning_thresholds(),
        "build_display_thresholds": adaptive_thresholds.build_display_thresholds(),
        "beta_classification": [adaptive_thresholds.beta_classification(b) for b in (-0.5, 0.3, 0.9, 1.1, 1.6, 2.5)],
    }
    _check("adaptive_thresholds", observed)


def test_regime_detection() -> None:
    detector = MarketRegimeDetector()
    observed: dict[str, Any] = {}
    for name, kind in CONTEXTS:
        prices = SERIES[name]
        for fear_greed in (None, 15, 85):
            result = detector.detect(prices, name.upper(), fear_greed=fear_greed, asset_type=kind)
            observed[f"{name}_{kind}_fg{fear_greed}"] = {
                "result": result,
                "six_phase": MarketRegimeDetector.refine_to_6phase(result, prices),
            }
        observed[f"{name}_{kind}_multi"] = detector.detect_multi_timeframe(prices, name.upper(), 50, 55.0, kind)
        observed[f"{name}_{kind}_vix"] = detector.detect(prices, name.upper(), asset_type=kind, vix=32.0)
    observed["short"] = detector.detect(SERIES["bull"][:8], "SHORT")
    _check("regime_detection", observed)


def test_anomaly_detection() -> None:
    detector = AnomalyDetector()
    observed: dict[str, Any] = {}
    for name, kind in CONTEXTS:
        prices = SERIES[name]
        for label, factor in (("normal", 1.0), ("spike", 1.35), ("drop", 0.7)):
            series = with_spike(prices, factor)
            observed[f"{name}_{label}"] = detector.detect(name.upper(), series, series[-1], prices[0], asset_type=kind)
    observed["short"] = detector.detect("SHORT", SERIES["bull"][:6], SERIES["bull"][5], SERIES["bull"][0])
    _check("anomaly_detection", observed)


def test_drift() -> None:
    observed = {}
    for name in SERIES:
        prices = np.array(SERIES[name])
        observed[name] = check_drift(prices[:180], prices[180:], name.upper())
    observed["regime_change"] = check_drift(np.array(SERIES["calm"]), np.array(SERIES["bear"][-60:]), "SHIFT")
    observed["too_short"] = check_drift(np.array(SERIES["bull"][:5]), np.array(SERIES["bull"][5:8]), "TINY")
    _check("drift", observed)


@pytest.mark.parametrize("name", ["bull", "bear", "range", "calm"])
def test_forecast(name: str) -> None:
    forecaster = PriceForecaster()
    prices = SERIES[name]
    observed = {f"single_{horizon}": forecaster.forecast(prices, dates(len(prices)), horizon) for horizon in (7, 30)}
    observed["ensemble_7"] = forecaster.ensemble_forecast(prices, dates(len(prices)), 7)
    observed["ensemble_30"] = forecaster.ensemble_forecast(
        prices, dates(len(prices)), 30, market_context=_context(name, "crypto")
    )
    _check(f"forecast_{name}", observed)


def test_hyperparameter_tuning(monkeypatch: pytest.MonkeyPatch) -> None:
    import optuna

    from app.ml import hyperparameter_tuner

    create_study = optuna.create_study
    monkeypatch.setattr(
        optuna, "create_study", lambda **kwargs: create_study(sampler=optuna.samplers.TPESampler(seed=0), **kwargs)
    )
    prices = SERIES["bull"]
    _check(
        "hyperparameter_tuning",
        {
            "xgboost": hyperparameter_tuner.tune_xgboost(prices, n_trials=3),
            "prophet": hyperparameter_tuner.tune_prophet(prices, dates(len(prices)), n_trials=2),
            "xgboost_short": hyperparameter_tuner.tune_xgboost(prices[:20], n_trials=2),
        },
    )


def test_forecast_short_series() -> None:
    forecaster = PriceForecaster()
    observed = {}
    for count in (3, 8, 16, 25):
        prices = SERIES["bull"][:count]
        observed[f"len_{count}"] = {
            "single": forecaster.forecast(prices, dates(count), 7),
            "ensemble": forecaster.ensemble_forecast(prices, dates(count), 7),
        }
    _check("forecast_short", observed)
