# Architecture Technique — InvestAI

## Vue d'ensemble

```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐
│   Frontend   │────▶│   Nginx      │────▶│   Backend     │
│  React/TS    │◀────│  Rev. Proxy  │◀────│   FastAPI     │
└─────────────┘     └──────────────┘     └───────┬───────┘
                                                  │
                          ┌───────────────────────┼───────────────────┐
                          │                       │                   │
                    ┌─────▼─────┐          ┌──────▼──────┐    ┌──────▼──────┐
                    │ PostgreSQL │          │    Redis    │    │   Celery    │
                    │ TimescaleDB│          │  Cache/MQ  │    │  Workers   │
                    └───────────┘          └────────────┘    └────────────┘
```

## Backend — Flux de Donnees

```
Request HTTP
  │
  ▼
RequestLoggingMiddleware (trace_id, timing)
  │
  ▼
CORS Middleware ──▶ Rate Limiter (SlowAPI)
  │
  ▼
API Router (v1)
  ├── /auth          → JWT + TOTP + lockout
  ├── /portfolios    → CRUD portefeuilles
  ├── /assets        → CRUD actifs multi-types
  ├── /transactions  → CRUD + import CSV
  ├── /analytics     → Sharpe, VaR, Markowitz, Monte Carlo
  ├── /predictions   → Ensemble ML forecasting
  ├── /alerts        → Seuils prix/performance
  ├── /reports       → PDF/Excel (ReportLab, OpenPyXL)
  ├── /ws/prices     → WebSocket temps reel (auth par message)
  └── /health        → Liveness + /health/ready (readiness)
```

## Pipeline ML — Flux de Prediction

```
1. Donnees historiques
   HistoricalDataFetcher ──▶ CoinGecko / Yahoo Finance
                               │
                               ▼
2. Cache Redis           hist:{symbol}:{type}:{days}  (TTL 1h)
                               │
                               ▼
3. Contexte marche       MarketContext (Fear&Greed, BTC dom, volatilite)
   RegimeDetector        ──▶ bull / bear / neutral + confidence
                               │
                               ▼
4. Ensemble Forecast     PriceForecaster.ensemble_forecast()
   ├── Prophet           (MAP, mcmc_samples=0, seasonality adaptative)
   ├── ARIMA             (auto_arima ou grid search p,d,q)
   ├── XGBoost           (27 features, random_state=42, train/val split)
   ├── EMA               (span adaptatif)
   ├── Linear            (regression lineaire + CI par residus)
   └── MeanReversion     (Ornstein-Uhlenbeck, contre-tendance)
        │
        ▼
5. Ponderation          Mini-backtest MAPE sur les 20% recents
   ├── CI calibration   Quantiles empiriques + EWMA volatilite
   └── Trend vote       Vote pondere des modeles
        │
        ▼
6. Post-processing      AdaptiveThresholds (seuils bear/bull)
   ├── Bearish drift    Correction baissiere si regime bear
   ├── CI floor         Largeur minimum selon asset_type
   └── SHAP             Explainability (top 3 features)
        │
        ▼
7. Stockage             prediction_logs (PG) + pred:{sym}:{days} (Redis 6h)
   ├── price_at_creation  Baseline pour direction_correct
   ├── prediction_data    Features d'entree (JSON)
   └── models_detail      Poids et MAPE par modele
```

## Taches Celery (Planifiees)

| Tache | Frequence | Fonction |
|-------|-----------|----------|
| update-crypto-prices | 5 min | Rafraichir les prix crypto |
| update-stock-prices | 5 min | Rafraichir les prix actions/ETF |
| sync-exchanges | 1h | Synchroniser les exchanges (Binance, Kraken, Crypto.com) |
| check-alerts | 5 min | Verifier les alertes prix/performance |
| run-daily-predictions | 24h | Predictions ML pour tous les actifs |
| check-prediction-accuracy | 24h | Comparer predictions vs prix reels |
| check-data-drift | 24h | PSI drift detection |
| tune-hyperparameters | 7j | Optuna tuning (XGBoost + Prophet) |
| cache-historical-data | 30 min | Pre-cache des historiques |
| create-daily-snapshots | 00:00 UTC | Snapshots portefeuille |

## Securite

| Couche | Mecanisme |
|--------|-----------|
| Auth | JWT 15min + refresh 7j (httpOnly cookies) |
| MFA | TOTP (pyotp) + anti-rejeu Redis 90s |
| Lockout | 10 echecs → blocage 15min par compte |
| Chiffrement | Fernet (cles API exchanges) |
| Mots de passe | bcrypt cost 12+ |
| API errors | Messages generiques (pas de str(exc)) |
| WebSocket | Auth par premier message (pas en URL) |
| Cache ML | HMAC-SHA256 sur payloads serialises |
| Rate limit | SlowAPI sur toutes les routes |
| CORS | Origines strictes, methodes restreintes |
| trace_id | X-Request-ID propage dans tous les logs |
