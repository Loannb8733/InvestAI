import numpy as np
import pytest

from app.ml import hyperparameter_tuner
from app.ml.forecasting.ensemble import PriceForecaster
from app.ml.forecasting.models.prophet import prophet_forecast
from tests.ml.series import SERIES, dates

pytestmark = pytest.mark.usefixtures("empty_test_redis")


def test_les_intervalles_de_prophet_ne_changent_plus_d_une_requete_a_l_autre() -> None:
    prices = SERIES["bull"]
    runs = []
    for global_seed in (1, 2):
        np.random.seed(global_seed)
        runs.append(prophet_forecast(prices, dates(len(prices)), 7, {}))
    assert runs[0].confidence_low == runs[1].confidence_low
    assert runs[0].confidence_high == runs[1].confidence_high


def test_prophet_laisse_l_alea_global_de_numpy_tel_qu_il_l_a_trouve() -> None:
    prices = SERIES["bull"]
    np.random.seed(5)
    expected = np.random.random()
    np.random.seed(5)
    prophet_forecast(prices, dates(len(prices)), 7, {})
    assert np.random.random() == expected


def test_le_reglage_optuna_donne_les_memes_parametres_a_chaque_execution() -> None:
    prices = SERIES["bull"]
    assert hyperparameter_tuner.tune_xgboost(prices, n_trials=3) == hyperparameter_tuner.tune_xgboost(
        prices, n_trials=3
    )


def test_xgboost_reste_dans_l_ensemble_quand_on_lui_fournit_les_volumes() -> None:
    prices = SERIES["bull"]
    volumes = [1000.0 + 10.0 * i for i in range(len(prices))]
    result = PriceForecaster().ensemble_forecast(prices, dates(len(prices)), 7, volumes=volumes)
    assert "XGBoost" in {detail["name"] for detail in result.models_detail}
