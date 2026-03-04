# MAINTENANCE_IA.md — Guide de Maintenance du Pipeline IA

## 1. Architecture ML

```
backend/app/ml/
├── forecaster.py            # Ensemble: Prophet + ARIMA + XGBoost + EMA + Linear + MeanReversion
├── anomaly_detector.py      # Isolation Forest + Z-score
├── drift_detector.py        # PSI (Population Stability Index) pour detecter la derive
├── adaptive_thresholds.py   # Seuils dynamiques selon le contexte marche
├── regime_detector.py       # Detection de regime (bull/bear/neutral)
├── hyperparameter_tuner.py  # Optuna tuning (Prophet + XGBoost)
├── market_context.py        # Fear & Greed, BTC dominance, volatilite
└── historical_data.py       # Fetch historique (CoinGecko, Yahoo Finance)
```

## 2. Comment Reentrainer les Modeles

### Automatique (recommande)
Les modeles sont reentraines automatiquement via les taches Celery :

| Tache | Frequence | Fichier |
|-------|-----------|---------|
| `run_daily_predictions` | Quotidien | `tasks/predictions.py` |
| `tune_hyperparameters` | Hebdomadaire (7j) | `tasks/predictions.py` |
| `check_prediction_accuracy` | Quotidien | `tasks/predictions.py` |
| `check_data_drift` | Quotidien | `tasks/predictions.py` |

### Manuel
```bash
# Depuis le conteneur backend
docker compose exec backend python -c "
from app.tasks.predictions import tune_hyperparameters, run_daily_predictions
tune_hyperparameters.delay()  # Lance le tuning Optuna
run_daily_predictions.delay() # Relance les predictions
"
```

### Reentrainement apres derive detectee
Si les logs affichent `DATA DRIFT detected`, les modeles doivent etre revalides :
1. Vider le cache des hyperparametres : `docker compose exec redis redis-cli KEYS "hparams:*" | xargs redis-cli DEL`
2. Vider le cache des modeles : `docker compose exec redis redis-cli KEYS "model:*" | xargs redis-cli DEL`
3. Relancer le tuning : `tune_hyperparameters.delay()`

## 3. Ou Trouver les Logs d'Erreurs

### Logs de calcul ML
```bash
# Tous les logs backend (inclut ML)
docker compose logs -f backend | grep -E "WARNING|ERROR"

# Logs specifiques ML
docker compose logs -f backend | grep -E "forecaster|anomaly|drift|prediction"

# Logs Celery (taches ML)
docker compose logs -f celery | grep -E "WARNING|ERROR|prediction|drift"
```

### Logs structures (production)
En production (`APP_ENV=production`), les logs sont en JSON :
```json
{
  "timestamp": "2026-03-03T12:00:00Z",
  "level": "WARNING",
  "logger": "app.ml.forecaster",
  "message": "Prophet failed: ...",
  "trace_id": "a1b2c3d4e5f6g7h8"
}
```

### Fichiers cles pour le debugging
| Probleme | Fichier | Pattern de log |
|----------|---------|----------------|
| Prediction echouee | `prediction_service.py` | `Failed to save prediction log` |
| Modele divergent | `forecaster.py` | `Prophet failed`, `ARIMA ensemble`, `XGBoost ensemble` |
| Derive des donnees | `drift_detector.py` | `DATA DRIFT detected` |
| Accuracy degradee | `tasks/predictions.py` | `DRIFT ALERT: ... MAPE=` |
| Cache Redis | `core/redis_client.py` | `HMAC verification failed` |

## 4. Seuils d'Alerte pour la Derive (Drift)

### PSI (Population Stability Index)
Le PSI est calcule sur 4 features : returns, volatilite 10j, momentum 5j, log-prix.

| PSI | Statut | Action |
|-----|--------|--------|
| < 0.10 | `ok` | Aucune action |
| 0.10 - 0.20 | `warning` | Surveiller, verifier les accuracy recentes |
| > 0.20 | `drift` | Retuner les hyperparametres, vider les caches modeles |

**Fichier de configuration** : `backend/app/ml/drift_detector.py`
```python
PSI_OK = 0.1
PSI_WARNING = 0.2
```

### MAPE (Mean Absolute Percentage Error)
Seuils d'alerte pour les predictions verifiees (dans `tasks/predictions.py`) :

| Type d'actif | Seuil MAPE | Action |
|-------------|------------|--------|
| Crypto | > 20% | Log `DRIFT ALERT` |
| Actions/ETF | > 10% | Log `DRIFT ALERT` |

### Direction correcte
Le champ `direction_correct` dans `prediction_logs` compare la direction predite vs reelle.
Un taux de direction correcte < 50% sur 30 jours indique un modele degrade.

## 5. Seeds et Reproductibilite

Tous les modeles utilisent des seeds fixes pour la reproductibilite :

| Composant | Seed/Config | Fichier |
|-----------|-------------|---------|
| XGBoost | `random_state=42` | `forecaster.py`, `hyperparameter_tuner.py` |
| Prophet | `mcmc_samples=0` (MAP estimation) | `forecaster.py`, `hyperparameter_tuner.py` |
| CmdStan | Version 2.38.0 pinned | `backend/Dockerfile` |
| Optuna | `optuna==3.5.0` | `requirements.txt` |
| Isolation Forest | `random_state=42` (defaut sklearn) | `anomaly_detector.py` |

## 6. Cache Redis des Modeles

| Cle Redis | TTL | Contenu |
|-----------|-----|---------|
| `pred:{symbol}:{days}` | 6h | Resultat de prediction (JSON) |
| `ensemble:{symbol}:{hash}:{days}` | 4h | Resultat ensemble (JSON) |
| `model:{symbol}:{name}:{hash}` | 24h | Modele serialise (HMAC-SHA256 signe) |
| `hparams:{symbol}:{model}` | 7j | Hyperparametres optimaux (JSON) |
| `hist:{symbol}:{type}:{days}` | 1h | Donnees historiques (JSON) |
| `reliability:{symbol}:{days}` | 24h | Scores de fiabilite (JSON) |

### Securite du cache
Les modeles serialises sont signes avec HMAC-SHA256 (`SECRET_KEY`).
Si le HMAC echoue au chargement, le cache est ignore et un warning est logge :
`HMAC verification failed for model {symbol}:{model_name}`

## 7. Tests ML

```bash
# Tests de stress (outliers, nulls, types inattendus, determinisme)
docker compose exec backend python -m pytest tests/unit/test_stress_ml.py -v

# Tests du forecaster
docker compose exec backend python -m pytest tests/unit/test_forecaster.py -v

# Tous les tests unitaires
docker compose exec backend python -m pytest tests/unit/ -v

# Avec couverture
docker compose exec backend python -m pytest tests/unit/ --cov=app/ml
```

## 8. Checklist de Mise a Jour des Dependances ML

Avant de mettre a jour une dependance ML :
1. Lancer `tests/unit/test_stress_ml.py` — tous les tests doivent passer
2. Verifier le determinisme (classe `TestDeterminism`) — resultats identiques a 10^-6
3. Comparer les predictions avant/apres sur 3 symboles (BTC, ETH, AAPL)
4. Verifier que SHAP fonctionne encore (`shap.TreeExplainer` sur XGBoost)
5. Mettre a jour le pin dans `requirements.txt` avec la version exacte (`==`)
