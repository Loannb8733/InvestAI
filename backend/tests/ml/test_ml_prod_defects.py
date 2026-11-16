"""Défauts du moteur de prévision corrigés pour la production (lot 1 du projet d'études)."""

from datetime import datetime
from typing import Any

import numpy as np
import pytest

from app.ml.forecasting import ensemble
from app.ml.forecasting.ensemble import PriceForecaster
from app.ml.forecasting.models.simple import linear_forecast
from app.ml.forecasting.models.xgboost import xgboost_forecast
from app.ml.forecasting.types import ForecastResult
from app.ml.forecasting.weighting import compute_weights
from tests.ml.series import SERIES, dates

pytestmark = pytest.mark.usefixtures("empty_test_redis")


def _path(values: list[float]) -> ForecastResult:
    return ForecastResult([], list(values), list(values), list(values), "neutral", 0.0, "double")


def test_un_modele_en_erreur_est_signale_parmi_les_modeles_ecartes(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*args: Any, **kwargs: Any) -> ForecastResult:
        raise RuntimeError("panne simulée")

    monkeypatch.setattr(ensemble, "xgboost_forecast", broken)
    prices = SERIES["bull"]
    result = PriceForecaster().ensemble_forecast(prices, dates(len(prices)), 7)
    assert "XGBoost" not in {d["name"] for d in result.models_detail}
    assert {"name": "XGBoost", "reason": "erreur : RuntimeError: panne simulée"} in result.skipped_models


def test_un_modele_absent_ou_a_l_historique_trop_court_est_signale() -> None:
    forecaster = PriceForecaster()
    forecaster.prophet_available = False
    prices = SERIES["bull"][:25]
    result = forecaster.ensemble_forecast(prices, dates(len(prices)), 7)
    reasons = {s["name"]: s["reason"] for s in result.skipped_models}
    assert reasons["Prophet"] == "non installé"
    assert reasons["XGBoost"] == "historique insuffisant (25 cours, 30 requis)"


def test_un_modele_a_la_prevision_aberrante_est_ecarte_seul(monkeypatch: pytest.MonkeyPatch) -> None:
    def soaring(prices: list[float], dates: list[datetime], days: int, *args: Any, **kwargs: Any) -> ForecastResult:
        return _path([prices[-1] * 3] * days)

    monkeypatch.setattr(ensemble, "ema_forecast", soaring)
    prices = SERIES["calm"]
    result = PriceForecaster().ensemble_forecast(prices, dates(len(prices)), 7)
    assert {"name": "EMA", "reason": "prévision aberrante (au-delà de ±50 %)"} in result.skipped_models
    assert abs(result.prices[-1] / prices[-1] - 1) < 0.5


def test_un_modele_moins_precis_que_la_prevision_naive_en_backtest_est_ecarte(monkeypatch: pytest.MonkeyPatch) -> None:
    def biased(prices: list[float], dates: list[datetime], days: int, *args: Any, **kwargs: Any) -> ForecastResult:
        return _path([prices[-1] * 1.1] * days)

    monkeypatch.setattr(ensemble, "ema_forecast", biased)
    prices = SERIES["calm"]
    result = PriceForecaster().ensemble_forecast(prices, dates(len(prices)), 7)
    reasons = {s["name"]: s["reason"] for s in result.skipped_models}
    assert reasons["EMA"].startswith("moins précis que la prévision naïve en backtest")
    assert "Naive" in {d["name"] for d in result.models_detail}
    assert sum(d["weight_pct"] for d in result.models_detail) in (99, 100, 101)


def test_une_fenetre_de_backtest_en_echec_est_exclue_au_lieu_de_compter_50() -> None:
    prices = [100.0] * 120
    calls = {"flaky": 0}

    def run(name: str, train: list[float], train_dates: list[datetime], horizon: int) -> ForecastResult:
        if name == "flaky":
            calls["flaky"] += 1
            if calls["flaky"] % 2:
                raise ValueError("fenêtre impossible")
        return _path([101.0] * horizon)

    _, _, mapes = compute_weights(prices, dates(120), [("steady", _path([])), ("flaky", _path([]))], run)
    assert mapes[1] == pytest.approx(1.0)


def test_un_modele_sans_aucune_fenetre_reussie_est_ecarte_de_l_ensemble(monkeypatch: pytest.MonkeyPatch) -> None:
    original = PriceForecaster.run_model

    def run_model(self: PriceForecaster, name: str, prices: list[float], *args: Any, **kwargs: Any) -> ForecastResult:
        if name == "EMA" and len(prices) < len(SERIES["bull"]):
            raise ValueError("backtest impossible")
        return original(self, name, prices, *args, **kwargs)

    monkeypatch.setattr(PriceForecaster, "run_model", run_model)
    prices = SERIES["bull"]
    result = PriceForecaster().ensemble_forecast(prices, dates(len(prices)), 7)
    assert "EMA" not in {d["name"] for d in result.models_detail}
    assert {"name": "EMA", "reason": "backtest en échec sur toutes les fenêtres"} in result.skipped_models


def test_les_hyperparametres_d_un_symbole_ne_passent_pas_au_suivant(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, list[dict[str, Any]]] = {}
    tuned = {"AAA": {"xgboost": {"max_depth": 7}}}
    monkeypatch.setattr(ensemble, "cached_hyperparams", lambda symbol: tuned.get(symbol))

    def spy(prices: list[float], d: list[datetime], days: int, params: dict[str, Any], **_: Any) -> ForecastResult:
        seen.setdefault(current, []).append(params)
        return _path([prices[-1]] * days)

    monkeypatch.setattr(ensemble, "xgboost_forecast", spy)
    forecaster = PriceForecaster()
    prices = SERIES["calm"]
    for current in ("AAA", "BBB"):
        forecaster.ensemble_forecast(prices, dates(len(prices)), 7, symbol=current)
    assert {p.get("max_depth") for p in seen["AAA"]} == {7}
    assert {p.get("max_depth") for p in seen["BBB"]} == {None}
    assert forecaster.hyperparams == {}


def test_linear_part_du_dernier_prix_et_non_de_la_droite_de_regression() -> None:
    prices = [100.0 * (1.002**i) for i in range(300)] + [60.0 * (1.002**i) for i in range(65)]
    result = linear_forecast(prices, dates(len(prices)), 7)
    assert result.prices[0] == pytest.approx(prices[-1], rel=0.05)


def test_xgboost_ne_remonte_pas_vers_d_anciens_niveaux_de_prix() -> None:
    rng = np.random.RandomState(0)
    noise = np.exp(0.01 * rng.standard_normal(365))
    prices = [float(p) for p in np.concatenate([np.full(300, 100.0), np.full(65, 10.0)]) * noise]
    result = xgboost_forecast(prices, dates(len(prices)), 30, {})
    assert max(result.prices) < 15.0
    assert min(result.prices) > 6.0
