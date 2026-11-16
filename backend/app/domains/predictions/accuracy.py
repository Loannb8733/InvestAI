from datetime import date, datetime, timedelta
from decimal import Decimal

from app.domains.market_data.history.series import PriceSeries
from app.domains.predictions.models import PredictionLog

SETTLE_DELAY = timedelta(days=1)
GIVE_UP_AFTER = timedelta(days=7)
LOOKBACK_DAYS = 3


def _direction_correct(price_at_creation: Decimal | None, predicted_price: float, actual_price: float) -> bool | None:
    if price_at_creation is None:
        return None
    baseline = float(price_at_creation)
    if baseline > 0:
        return (predicted_price > baseline) == (actual_price > baseline)
    return None


def price_on(series: PriceSeries, day: date) -> float | None:
    """Cours enregistré pour ``day``, ou à défaut le dernier des trois jours précédents (week-end, jour férié)."""
    known = {moment.date(): price for moment, price in zip(series.dates, series.prices, strict=False)}
    for back in range(LOOKBACK_DAYS + 1):
        price = known.get(day - timedelta(days=back))
        if price is not None and price > 0:
            return float(price)
    return None


def record_outcome(log: PredictionLog, actual_price: float, now: datetime) -> float | None:
    """Complète une prédiction échue (cours réel, MAPE, direction, couverture de l'intervalle) ; renvoie le seuil de
    MAPE franchi (20 % en crypto, 10 % sinon), None sans dérive."""
    log.actual_price = actual_price
    log.accuracy_checked = now
    if not (actual_price > 0 and log.predicted_price):
        return None

    log.mape = abs(log.predicted_price - actual_price) / actual_price * 100
    log.direction_correct = _direction_correct(log.price_at_creation, log.predicted_price, actual_price)
    if log.confidence_low is not None and log.confidence_high is not None:
        log.ci_covered = log.confidence_low <= actual_price <= log.confidence_high
    else:
        log.ci_covered = None

    threshold = 20.0 if log.asset_type == "crypto" else 10.0
    return threshold if log.mape > threshold else None


def give_up(log: PredictionLog, now: datetime) -> bool:
    """Clôt sans mesure une prédiction dont le cours de la date cible manque encore une semaine après ; vrai si
    elle est close."""
    if log.target_date is None or now - log.target_date <= GIVE_UP_AFTER:
        return False
    log.accuracy_checked = now
    return True
