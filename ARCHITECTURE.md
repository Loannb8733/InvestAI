# InvestAI — Cartographie Complète des Modules

> Généré le 04/03/2026 — Audit exhaustif frontend + backend

---

## Table des matières

1. [Vue d'ensemble](#vue-densemble)
2. [Gestion Assets & Data](#1--gestion-assets--data)
   - [Dashboard](#dashboard-)
   - [Portefeuille](#portefeuille-portfolio)
   - [Transactions](#transactions-transactions)
   - [Exchanges](#exchanges-exchanges)
3. [Analyse & Projection](#2--analyse--projection)
   - [Analyses](#analyses-analytics)
   - [Projections](#projections-predictions)
   - [Simulations](#simulations-simulations)
4. [Intelligence Artificielle](#3--intelligence-artificielle)
   - [Insights](#insights-insights)
   - [Smart Insights](#smart-insights-smart-insights)
   - [Objectifs](#objectifs-goals)
5. [Monitoring & Suivi](#4--monitoring--suivi)
   - [Alertes](#alertes-alerts)
   - [Journal](#journal-notes)
   - [Calendrier](#calendrier-calendar)
   - [Rapports](#rapports-reports)
6. [Système](#5--système)
   - [Paramètres](#paramètres-settings)
   - [Admin](#admin-admin)
7. [Architecture Technique](#architecture-technique)
8. [Stack ML/IA](#stack-mlia)
9. [APIs Externes](#apis-externes)
10. [Stratégie de Cache](#stratégie-de-cache)
11. [Matrice de Priorité](#matrice-de-priorité)

---

## Vue d'ensemble

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React 18)                      │
│  Zustand (auth) │ React Query (data) │ Recharts │ shadcn/ui     │
├─────────────────────────────────────────────────────────────────┤
│                     API Layer (Axios + JWT)                      │
├─────────────────────────────────────────────────────────────────┤
│                    BACKEND (FastAPI + Python 3.11)               │
│  21 endpoint files │ 10+ services │ 7 ML models │ Celery tasks  │
├─────────────────────────────────────────────────────────────────┤
│              PostgreSQL + TimescaleDB │ Redis │ Celery           │
└─────────────────────────────────────────────────────────────────┘
```

**15 modules** dans la sidebar + 1 module Admin (admin only) = **16 pages applicatives**.

---

## 1 — Gestion Assets & Data

### Dashboard (`/`)

| Aspect | Détail |
|--------|--------|
| **Page** | `frontend/src/pages/DashboardPage.tsx` |
| **Route backend** | `backend/app/api/v1/endpoints/dashboard.py` |
| **Service** | `metrics_service.py`, `snapshot_service.py`, `price_service.py` |

#### Contenu UI
- **5 cartes métriques** : Patrimoine Total, Capital Net, Plus-value Nette, Variation (période), Portefeuilles
- **Card PnL** : P&L Latent, P&L Réalisé, Total Frais, P&L Total, P&L Net
- **Cards Risque** : Volatilité annualisée, Ratio de Sharpe, VaR 95%, Max Drawdown, HHI Concentration, Stress Tests (-20%/-40%)
- **Card ROI** : ROI Annualisé (CAGR), Concentration HHI
- **PerformanceChart** (Recharts AreaChart) : Valeur / Total investi / Capital net sur la période
- **AllocationChart** (Recharts PieChart) : Répartition par actif et par classe
- **BenchmarkChart** : Comparaison normalisée vs BTC, ETH, SOL
- **Top/Worst performers** : Meilleures et pires performances
- **Transactions récentes** : 5 dernières transactions
- **Alertes & événements** : Prochaines alertes et événements calendrier
- **Widgets drag-and-drop** personnalisables (ordre + visibilité persistés en localStorage)
- **Export PDF** du dashboard complet
- **Prix temps réel** via WebSocket

#### Endpoints Backend
```
GET  /api/v1/dashboard?days={0|1|7|30|90|365}
GET  /api/v1/dashboard/benchmarks?days=
GET  /api/v1/dashboard/portfolio/{id}
GET  /api/v1/dashboard/portfolio/{id}/history
GET  /api/v1/dashboard/recent-transactions
GET  /api/v1/dashboard/active-alerts
GET  /api/v1/dashboard/upcoming-events
GET  /api/v1/dashboard/historical-data
POST /api/v1/dashboard/backfill-prices
GET  /api/v1/dashboard/backfill-status
WS   /api/v1/ws/prices (WebSocket temps réel)
```

#### Data Flow
1. `metrics_service.get_user_dashboard_metrics(db, user_id, days)` agrège toutes les métriques
2. `snapshot_service.build_portfolio_value_series(db, user_id, days)` reconstruit la série historique :
   - Replay des transactions jour par jour
   - Prix source : PostgreSQL `asset_price_history` (6220 points) → Redis → CoinGecko/Yahoo
   - LOCF (Last Observation Carried Forward) uniquement si aucun prix disponible
3. `snapshot_service.get_all_risk_metrics()` calcule :
   - Volatilité annualisée (σ × √252)
   - Sharpe = (CAGR - 3.5%) / σ
   - VaR 95% = percentile 5% des rendements journaliers × patrimoine
   - CVaR = moyenne des pertes au-delà de VaR
   - Max Drawdown = pire chute peak-to-trough
   - HHI = Σ(poids²) × 10000
   - Stress tests = patrimoine × scénario
4. Sélecteur de période : `days=0` (tout), `1` (24h), `7`, `30`, `90`, `365`

#### État : ✅ 100% fonctionnel
- Données réelles (6220 prix en PostgreSQL)
- `is_data_estimated: false` sur tous les points
- Bandeau "Données estimées" supprimé
- 20/20 tests de cohérence (`verify_dashboard_math.py`)

---

### Portefeuille (`/portfolio`)

| Aspect | Détail |
|--------|--------|
| **Page** | `frontend/src/pages/PortfolioPage.tsx` |
| **Routes backend** | `portfolios.py`, `assets.py`, `transactions.py` |
| **Service** | `metrics_service.py`, `price_service.py` |

#### Contenu UI
- **Sélecteur de portefeuilles** (boutons)
- **Liste d'assets** avec icônes crypto, quantité, prix moyen, valeur actuelle, P&L
- **Onglets** : Holdings actuels / Historique (assets vendus)
- **Badges** cold wallet, filtres par plateforme
- **Groupement multi-plateforme** (Binance, Kraken, Cold Wallet...)
- **CRUD** : Ajouter/modifier/supprimer assets et portefeuilles
- **Import CSV** (auto-détection Binance/Kraken/Crypto.com/Generic)
- **Export CSV** des transactions

#### Endpoints Backend
```
GET/POST/PATCH/DELETE  /api/v1/portfolios
GET/POST/PATCH/DELETE  /api/v1/assets
PUT/DELETE             /api/v1/portfolios/{id}/cash-balance
POST                   /api/v1/transactions/import-csv
GET                    /api/v1/transactions/export-csv
GET                    /api/v1/dashboard/portfolio/{id}
GET                    /api/v1/dashboard/portfolio/{id}/history
```

#### Data Flow
- Assets groupés par `exchange_platform` (Binance, Kraken, Cold Wallet)
- Chaque asset : `quantity × current_price = value`, `value - (quantity × avg_buy_price) = P&L`
- Historique : assets avec `quantity = 0` et transactions de vente → P&L réalisé
- Import CSV : détection automatique du format par analyse des headers

#### État : ✅ 100% fonctionnel

---

### Transactions (`/transactions`)

| Aspect | Détail |
|--------|--------|
| **Page** | `frontend/src/pages/TransactionsPage.tsx` |
| **Route backend** | `backend/app/api/v1/endpoints/transactions.py` |
| **Service** | Recalcul automatique `quantity` et `avg_buy_price` sur l'asset |

#### Contenu UI
- **Tableau TanStack Table** avec tri, filtres, pagination
- **Badges colorés** par type : BUY (vert), SELL (rouge), TRANSFER, AIRDROP, etc.
- **Montants** : vert = entrée, rouge = sortie
- **CRUD** : créer, éditer, supprimer une transaction
- **Import/Export CSV**
- **Suppression en masse** (reset all)

#### Types de transactions supportés
```
BUY, SELL, TRANSFER_IN, TRANSFER_OUT,
CONVERSION_IN, CONVERSION_OUT,
AIRDROP, STAKING_REWARD, DIVIDEND, INTEREST, FEE
```

#### Endpoints Backend
```
GET/POST/PATCH/DELETE  /api/v1/transactions
DELETE                 /api/v1/transactions/all
GET                    /api/v1/transactions/csv-platforms
POST                   /api/v1/transactions/import-csv
GET                    /api/v1/transactions/export-csv
```

#### Data Flow
- Création de transaction → mise à jour automatique `asset.quantity` et `asset.avg_buy_price`
- Suppression → revert de la quantité
- Import CSV : auto-detect plateforme, déduplique par `external_id`, crée assets manquants

#### État : ✅ 100% fonctionnel

---

### Exchanges (`/exchanges`)

| Aspect | Détail |
|--------|--------|
| **Page** | `frontend/src/pages/ExchangesPage.tsx` |
| **Route backend** | `backend/app/api/v1/endpoints/api_keys.py` |
| **Services** | `backend/app/services/exchanges/` (10 adapters) |

#### Contenu UI
- **Cards** par exchange avec logo (PNG/SVG + fallback couleur)
- **Table API keys** : clé masquée, statut, dernière sync, erreurs
- **Dialogue création** : sélecteur exchange, champs API key + secret
- **Boutons** : Test connexion, Sync positions/balances
- **Copy** API key (affichage masqué)

#### Exchanges supportés (10)
```
Binance, Kraken, Crypto.com, Coinbase, Bybit,
Kucoin, Gate.io, OKX, Bitstamp, Bitpanda
```

#### Endpoints Backend
```
GET    /api/v1/api-keys/exchanges    (liste des exchanges supportés)
GET/POST/PATCH/DELETE  /api/v1/api-keys
POST   /api/v1/api-keys/test         (test connexion)
POST   /api/v1/api-keys/sync         (sync balances + trades)
```

#### Data Flow
- Clés API chiffrées **Fernet** en BDD (jamais en clair)
- Sync : chaque exchange a un adapter dédié (classe héritant de `BaseExchange`)
- Récupère : balances, positions, historique trades
- Crée automatiquement les transactions correspondantes

#### État : ✅ 100% fonctionnel

---

## 2 — Analyse & Projection

### Analyses (`/analytics`)

| Aspect | Détail |
|--------|--------|
| **Page** | `frontend/src/pages/AnalyticsPage.tsx` |
| **Route backend** | `backend/app/api/v1/endpoints/analytics.py` |
| **Service** | `analytics_service.py` |

#### Contenu UI
- **PieChart** : allocation par type et par actif
- **BarChart** : performance par asset
- **RadarChart** : profil risque multi-dimensionnel
- **CorrelationMatrix** : heatmap corrélation inter-assets (composant dédié)
- **MonteCarloCard** : résultats simulation Monte Carlo
- **StressTestCard** : scénarios de crash historiques
- **PortfolioEvolutionChart** : évolution historique du portefeuille
- **Métriques affichées** : Volatilité, Sharpe, Sortino, Calmar, Max Drawdown, VaR 95%, CVaR, Beta, HHI, XIRR

#### Endpoints Backend
```
GET  /api/v1/analytics                          (global)
GET  /api/v1/analytics/portfolio/{id}           (par portefeuille)
GET  /api/v1/analytics/correlation              (matrice corrélation)
GET  /api/v1/analytics/diversification          (HHI + recommandations)
GET  /api/v1/analytics/performance              (1d/7d/30d/90d/1y/all)
GET  /api/v1/analytics/risk-metrics             (profil risque complet)
GET  /api/v1/analytics/stress-test              (scénarios historiques)
GET  /api/v1/analytics/beta                     (beta vs BTC, SPY)
GET  /api/v1/analytics/monte-carlo?horizon=&simulations=
GET  /api/v1/analytics/xirr                     (taux rendement interne)
GET  /api/v1/analytics/optimize?objective=       (optimisation MPT)
POST /api/v1/analytics/rebalance                (ordres rebalancing)
```

#### Data Flow détaillé

**Corrélation** :
- Matrice Spearman sur prix historiques (min 30 jours communs)
- Identifie paires fortement corrélées (>0.7) et négativement corrélées (<-0.3)

**Monte Carlo** :
- 5000 simulations par défaut
- Horizon : 7 à 365 jours
- Méthode : rendements journaliers aléatoires (distribution historique)
- Output : percentiles (5%, 25%, 50%, 75%, 95%), prob(gain), prob(perte > 10%)

**Optimisation MPT** :
- Objectifs : `max_sharpe` ou `min_volatility`
- Calcul frontière efficiente via `scipy.optimize`
- Input : matrice covariance + rendements attendus
- Output : poids optimaux par asset

**Beta** :
- Calculé vs BTC et SPY (S&P 500)
- Régression linéaire des rendements journaliers

**Stress Tests** :
- Scénarios historiques : Black Monday 1987, Crise 2008, Flash Crash 2010, COVID 2020, Crypto Winter 2022
- Impact = allocation × choc sectoriel

**XIRR** :
- Taux de rendement interne pondéré par le temps
- Prend en compte toutes les transactions (entrées/sorties de cash)

**Benchmarks** : BTC, SPY (S&P 500). Taux sans risque : 3.5% EUR.

#### État : ✅ 100% fonctionnel — toutes les métriques sur données réelles

---

### Projections (`/predictions`)

| Aspect | Détail |
|--------|--------|
| **Page** | `frontend/src/pages/PredictionsPage.tsx` |
| **Route backend** | `backend/app/api/v1/endpoints/predictions.py` |
| **Services** | `prediction_service.py`, `forecaster.py`, `anomaly_detector.py`, `regime_detector.py` |

#### Contenu UI
- **Onglet Prédictions** : charts prix avec intervalles de confiance, trend (bullish/bearish/neutral), support/résistance, contributions modèles
- **Onglet Anomalies** : badges sévérité (low/medium/high), type (price_spike/price_drop/volatility_spike)
- **Onglet Sentiment** : jauge fear/greed (0-100), sentiment global, phase de marché
- **Onglet What-If** : simulateur de scénarios (% change par asset → impact portefeuille)

#### Endpoints Backend
```
GET  /api/v1/predictions/asset/{symbol}?days=    (prédiction par asset)
GET  /api/v1/predictions/portfolio?days=          (prédictions portefeuille)
GET  /api/v1/predictions/anomalies               (détection anomalies)
GET  /api/v1/predictions/sentiment               (sentiment marché)
POST /api/v1/predictions/what-if                  (simulation scénario)
GET  /api/v1/predictions/market-cycle             (cycle de marché)
GET  /api/v1/predictions/events                   (événements marché)
GET  /api/v1/predictions/track-record/{symbol}    (historique précision)
```

#### Ensemble de 7 modèles ML

| Modèle | Type | Usage |
|--------|------|-------|
| **Prophet** (Facebook) | Séries temporelles saisonnières | Capture tendances long terme + saisonnalité |
| **ARIMA / Auto-ARIMA** | Autorégressif | Modélisation statistique classique |
| **XGBoost** | Gradient boosting | Features techniques (RSI, MACD, Bollinger, MA) + SHAP explanations |
| **EMA** | Moyenne mobile exponentielle | Tendance court terme |
| **Régression linéaire** | Trend fitting | Tendance directionnelle |
| **Mean Reversion** | Ornstein-Uhlenbeck | Retour à la moyenne (stochastique) |

**Pondération** : par MAPE (Mean Absolute Percentage Error) — les modèles les plus précis historiquement ont plus de poids.

#### Détection d'anomalies
- **Isolation Forest** (scikit-learn) : 5% contamination, 100 estimators
- **Z-Score** : outlier statistique (|z| > 2.5)
- **Spike de volatilité** : seuils adaptatifs par régime de marché

#### Détection de régime (7 indicateurs techniques)
| Indicateur | Signal |
|-----------|--------|
| RSI | Momentum (surachat/survente) |
| MACD | Tendance (croisement signal) |
| Bollinger Bands | Volatilité & extrêmes |
| MA Cross (20/50/200) | Confirmation tendance |
| ROC | Momentum (rate of change) |
| Stochastic | Oscillateur momentum |
| Volume profile | Accumulation/distribution |

**4 phases** : bearish → bottom → bullish → top (avec probabilités)

#### Seuils adaptatifs (`adaptive_thresholds.py`)
- RSI : p90/p10 dynamiques au lieu de 70/30 fixes
- MACD : normalisé par volatilité journalière
- Bollinger : facteur 0.3-1.0 selon percentile de volatilité
- MA Cross : significatif si > 1σ sur 20 jours
- Stochastic : p95/p5 de l'historique

#### Fonctionnalités avancées
- **Walk-forward backtesting** (`backtester.py`) : MAPE, RMSE, MAE, R², Hit Rate
- **Drift detection** (`drift_detector.py`) : détecte quand les modèles dérivent
- **Hyperparameter tuning** (`hyperparameter_tuner.py`) : grid/random search

#### État : ✅ 100% fonctionnel — 7 modèles ML sur données réelles, cache Redis

---

### Simulations (`/simulations`)

| Aspect | Détail |
|--------|--------|
| **Page** | `frontend/src/pages/SimulationsPage.tsx` |
| **Route backend** | `backend/app/api/v1/endpoints/simulations.py` |

#### Contenu UI
- **Onglet FIRE Calculator** : formulaire (capital, revenus, dépenses, taux épargne, rendement) → chart projection + années restantes + montant mensuel nécessaire
- **Onglet Projection** : projection portefeuille sur N années → line chart multi-années + tableau annuel
- **Onglet DCA** : simulation Dollar-Cost Averaging → chart comparaison DCA vs lump sum

#### Endpoints Backend
```
POST /api/v1/simulations/fire       (calcul FIRE)
POST /api/v1/simulations/project    (projection portefeuille)
POST /api/v1/simulations/dca        (simulation DCA)
POST /api/v1/simulations/what-if    (scénario what-if)
GET  /api/v1/simulations/types      (types disponibles)
GET/POST/DELETE /api/v1/simulations  (sauvegarder/charger simulations)
```

#### Data Flow
- **FIRE** : `(dépenses_annuelles × 25)` = nombre FIRE, `(FIRE - capital) / épargne_mensuelle` = mois restants
- **Projection** : `capital × (1 + rendement)^n` avec contributions mensuelles
- **DCA** : achat régulier simulé sur prix historiques réels → comparaison performance

#### État : ✅ 90% fonctionnel — calculs backend, charts frontend. Améliorations UX possibles.

---

## 3 — Intelligence Artificielle

### Insights (`/insights`)

| Aspect | Détail |
|--------|--------|
| **Page** | `frontend/src/pages/InsightsPage.tsx` |
| **Route backend** | `backend/app/api/v1/endpoints/insights.py` |

#### Contenu UI
- **Onglet Analyse des Frais** : charts (frais mensuels, frais par exchange), total fees, ratio frais/capital
- **Onglet Tax-Loss Harvesting** : tableau des assets en perte → opportunités de vente fiscale
- **Onglet Revenus Passifs** : tracking staking rewards + dividendes + intérêts → total mensuel/annuel
- **Onglet DCA Backtest** : simulation DCA historique → performance comparée à la stratégie réelle

#### Endpoints Backend
```
GET /api/v1/insights/fees                (analyse des frais)
GET /api/v1/insights/tax-loss-harvesting (opportunités fiscales)
GET /api/v1/insights/passive-income      (revenus passifs)
GET /api/v1/insights/backtest-dca        (backtest DCA)
```

#### Data Flow
- **Frais** : `SUM(transactions.fee)` groupé par mois et par exchange
- **Tax-Loss** : filtre assets où `current_value < total_cost_basis` → gain fiscal potentiel
- **Passifs** : somme transactions de type `STAKING_REWARD` + `DIVIDEND` + `INTEREST`
- **DCA Backtest** : rejoue un DCA fictif sur prix historiques réels (PostgreSQL)

#### État : ✅ 85% fonctionnel — données réelles. Enrichissement tax-loss possible.

---

### Smart Insights (`/smart-insights`)

| Aspect | Détail |
|--------|--------|
| **Page** | `frontend/src/pages/SmartInsightsPage.tsx` |
| **Route backend** | `backend/app/api/v1/endpoints/smart_insights.py` |
| **Service** | `smart_insights_service.py` |

#### Contenu UI
- **Score de santé** (0-100) avec indicateur coloré :
  - 🟢 Excellent (80-100), 🟡 Good (60-79), 🟠 Fair (40-59), 🔴 Poor (0-39)
- **Cartes d'insights** par sévérité (info/warning/critical)
- **Suggestions de rebalancing** : ordres BUY/SELL pour atteindre l'allocation optimale (MPT)
- **Anomalies** avec impact EUR calculé
- **Régime de marché** : phase actuelle + signaux techniques
- **Sélecteur de jours** (30j par défaut)

#### Endpoints Backend
```
GET /api/v1/smart-insights/health?days=     (rapport santé complet)
GET /api/v1/smart-insights/rebalancing      (suggestions rebalancing)
GET /api/v1/smart-insights/anomalies-impact (anomalies + impact EUR)
```

#### Data Flow
1. `analytics_service` → métriques risque (volatilité, Sharpe, VaR, concentration)
2. `anomaly_detector` → Isolation Forest sur prix récents
3. `regime_detector` → 7 indicateurs techniques → phase de marché
4. MPT optimizer → allocation optimale → ordres de rebalancing
5. Score global = moyenne pondérée des sous-scores

**⚠️ Pas de LLM** (pas de GPT/Claude). Système **rule-based + ML classique** :
- Règles : "Volatilité > 80% → insight warning", "HHI > 3000 → concentration élevée"
- ML : Isolation Forest (anomalies), régression (régime), optimisation scipy (MPT)

#### État : ✅ 90% fonctionnel — insights algorithmiques. Potentiel ajout LLM pour insights textuels.

---

### Objectifs (`/goals`)

| Aspect | Détail |
|--------|--------|
| **Page** | `frontend/src/pages/GoalsPage.tsx` |
| **Route backend** | `backend/app/api/v1/endpoints/goals.py` |

#### Contenu UI
- **Cards objectifs** avec barre de progression
- **Montant cible** vs montant actuel
- **Jours restants** et **montant mensuel nécessaire**
- **Sélecteur de couleur** par objectif
- **Bouton Sync** : met à jour depuis la valeur du portefeuille
- **CRUD** : créer, modifier, supprimer

#### Endpoints Backend
```
GET/POST/PATCH/DELETE  /api/v1/goals
POST                   /api/v1/goals/{id}/sync
```

#### Data Flow
- `monthly_needed = (target_amount - current_amount) / months_remaining`
- Sync : `current_amount = portfolio_total_value` (ou un sous-ensemble)
- Progression : `current_amount / target_amount × 100`

#### État : ✅ 85% fonctionnel — CRUD + sync. Améliorations UX possibles (charts progression).

---

## 4 — Monitoring & Suivi

### Alertes (`/alerts`)

| Aspect | Détail |
|--------|--------|
| **Page** | `frontend/src/pages/AlertsPage.tsx` |
| **Route backend** | `backend/app/api/v1/endpoints/alerts.py` |
| **Service** | `alert_service.py`, `notification_service.py`, `email_service.py` |

#### Contenu UI
- **Cards stats** : total alertes, actives, déclenchées aujourd'hui
- **Tableau alertes** : nom, asset, condition, seuil, statut (active/triggered/disabled)
- **Dialogue création** : sélecteur asset, type condition, seuil, toggles email/in-app
- **Delete confirmation**

#### Conditions d'alerte (6)
```
price_above          Prix dépasse un seuil
price_below          Prix descend sous un seuil
change_percent_up    Hausse % sur période
change_percent_down  Baisse % sur période
daily_change_up      Hausse % journalière
daily_change_down    Baisse % journalière
```

#### Endpoints Backend
```
GET    /api/v1/alerts/conditions    (types disponibles)
GET    /api/v1/alerts/summary       (statistiques)
GET/POST/PATCH/DELETE /api/v1/alerts
POST   /api/v1/alerts/check         (vérification manuelle)
```

#### Data Flow
- Vérification automatique via **Celery beat** (toutes les 5 minutes)
- Fetch prix courant → compare au seuil → si déclenché :
  - Notification in-app (base de données)
  - Email SMTP (si activé)
  - Mise à jour statut `triggered`

#### État : ✅ 90% fonctionnel — alertes temps réel. Potentiel push notifications.

---

### Journal (`/notes`)

| Aspect | Détail |
|--------|--------|
| **Page** | `frontend/src/pages/NotesPage.tsx` |
| **Route backend** | `backend/app/api/v1/endpoints/notes.py` |

#### Contenu UI
- **Liste de notes** avec recherche full-text
- **Filtrage** par tags
- **Sentiment** : 🟢 Bullish / 🔴 Bearish / ⚪ Neutral (avec icônes)
- **Lien optionnel** vers un asset spécifique
- **Dialogue** création/édition
- **Card résumé** : total notes, tags les plus utilisés

#### Endpoints Backend
```
GET    /api/v1/notes/summary    (statistiques)
GET    /api/v1/notes/tags       (liste des tags)
GET/POST/PATCH/DELETE /api/v1/notes
```

#### Data Flow
- Note = `{ title, content, tags[], sentiment, asset_id? }`
- Recherche : `ILIKE '%query%'` sur titre et contenu
- Tags : extraction et agrégation côté backend

#### État : ✅ 85% fonctionnel — journal complet. Améliorable avec rich text editor.

---

### Calendrier (`/calendar`)

| Aspect | Détail |
|--------|--------|
| **Page** | `frontend/src/pages/CalendarPage.tsx` |
| **Route backend** | `backend/app/api/v1/endpoints/calendar.py` |

#### Contenu UI
- **Liste d'événements** avec filtres par type
- **Onglets** par catégorie d'événement
- **Dialogue** création/édition
- **Événements marché** (via `predictionsApi.getMarketEvents()`)
- **Cards résumé** : total événements, à venir, complétés, revenus attendus
- **Bouton "Compléter"** → auto-crée la prochaine occurrence si récurrent

#### Types d'événements (7)
```
dividend      Dividende
rent          Loyer
interest      Intérêts
payment_due   Paiement dû
rebalance     Rebalancing
tax_deadline  Échéance fiscale
reminder      Rappel
```

#### Endpoints Backend
```
GET    /api/v1/calendar/event-types
GET    /api/v1/calendar/summary
GET    /api/v1/calendar/upcoming?days=
GET/POST/PATCH/DELETE /api/v1/calendar
POST   /api/v1/calendar/{id}/complete
```

#### Data Flow
- Supporte **récurrences iCal** (daily, weekly, monthly, yearly)
- Complétion d'un événement récurrent → crée automatiquement la prochaine occurrence
- Revenus attendus : somme des montants des événements `dividend` + `rent` + `interest` à venir

#### État : ✅ 85% fonctionnel — calendrier complet. Vue calendrier visuel (grille) à ajouter.

---

### Rapports (`/reports`)

| Aspect | Détail |
|--------|--------|
| **Page** | `frontend/src/pages/ReportsPage.tsx` |
| **Route backend** | `backend/app/api/v1/endpoints/reports.py` |
| **Service** | `report_service.py` (ReportLab PDF, openpyxl Excel) |

#### Contenu UI
- **Cards par type** de rapport avec icône
- **Sélecteur d'année**
- **Boutons téléchargement** : PDF et Excel pour chaque type
- **Loading states** avec spinner

#### Types de rapports (3)
| Rapport | Contenu | Formats |
|---------|---------|---------|
| **Performance** | Métriques portefeuille, évolution, allocation, top/worst | PDF, Excel |
| **Déclaration fiscale** | Formulaire 2086 (crypto France), plus/moins-values par transaction | PDF, Excel |
| **Transactions** | Historique complet des transactions | PDF |

#### Endpoints Backend
```
GET /api/v1/reports/available-years
GET /api/v1/reports/performance/pdf
GET /api/v1/reports/performance/excel
GET /api/v1/reports/tax/{year}/pdf
GET /api/v1/reports/tax/{year}/excel
GET /api/v1/reports/transactions/pdf
```

#### Data Flow
- **Performance PDF** : ReportLab génère un document avec métriques, graphiques, allocation
- **Fiscal PDF** : calcul des plus/moins-values réalisées par transaction, formulaire 2086
- **Excel** : openpyxl avec sheets structurées (résumé, détail transactions, allocation)

#### État : ✅ 80% fonctionnel — génération réelle PDF/Excel. Templates enrichissables.

---

## 5 — Système

### Paramètres (`/settings`)

| Aspect | Détail |
|--------|--------|
| **Page** | `frontend/src/pages/SettingsPage.tsx` |
| **Route backend** | `backend/app/api/v1/endpoints/auth.py` |

#### Contenu UI
- **Profil** : nom, prénom, devise préférée (EUR/USD/GBP...)
- **Mot de passe** : ancien → nouveau → confirmation
- **MFA** : setup avec QR code TOTP, activer/désactiver, backup codes
- **Thème** : toggle dark/light mode

#### Endpoints Backend
```
GET   /api/v1/auth/me
PATCH /api/v1/auth/me
POST  /api/v1/auth/change-password
POST  /api/v1/auth/mfa/setup
POST  /api/v1/auth/mfa/verify
POST  /api/v1/auth/mfa/disable
GET   /api/v1/auth/mfa/backup-codes-count
POST  /api/v1/auth/mfa/regenerate-backup-codes
```

#### État : ✅ 100% fonctionnel

---

### Admin (`/admin`) — Admin only

| Aspect | Détail |
|--------|--------|
| **Page** | `frontend/src/pages/AdminPage.tsx` |
| **Route backend** | `backend/app/api/v1/endpoints/users.py` |

#### Contenu UI
- **Cards stats** : utilisateurs totaux, actifs, MFA activé
- **Tableau utilisateurs** : email, rôle, statut MFA, date création
- **Dialogue création** utilisateur
- **Toggle** actif/inactif, suppression

#### Endpoints Backend
```
GET/POST/PATCH/DELETE /api/v1/users    (admin only)
POST /api/v1/system/test-email         (test SMTP)
POST /api/v1/system/trigger-weekly-report
GET  /api/v1/system/status
```

#### État : ✅ 100% fonctionnel

---

## Architecture Technique

### Frontend
```
src/
├── pages/              22 pages (18 applicatives + 4 tests)
├── components/
│   ├── ui/             14 composants shadcn/ui
│   ├── layout/         4 (Layout, Header, Sidebar, NotificationBell)
│   ├── dashboard/      4 (MetricsRow, PnlCard, RiskCards, BenchmarkChart)
│   ├── charts/         2 (AllocationChart, PerformanceChart)
│   ├── analytics/      4 (CorrelationMatrix, MonteCarloCard, StressTestCard, EvolutionChart)
│   ├── forms/          6 (AddAsset, AddPortfolio, AddTransaction, EditTransaction, CashBalance, ImportCSV)
│   └── portfolio/      2 (AssetList, CreatePortfolioForm)
├── services/
│   └── api.ts          18 API client groups (Axios + JWT interceptor)
├── stores/
│   ├── authStore.ts    Auth state (Zustand + persist)
│   ├── portfolioStore.ts  Selected portfolio (Zustand)
│   └── notificationStore.ts  Unread count
├── hooks/
│   ├── useRealtimePrices.ts   WebSocket live prices
│   ├── useDashboardLayout.ts  Widget drag-and-drop persistence
│   ├── useExportPdf.ts        PDF export
│   └── use-toast.ts           Notifications UI
└── types/
    └── index.ts        Interfaces TypeScript (User, Asset, Transaction, etc.)
```

### Backend
```
app/
├── api/v1/endpoints/   21 fichiers endpoint
├── services/
│   ├── metrics_service.py      Dashboard métriques
│   ├── price_service.py        Multi-source prix (CoinGecko, Yahoo, Forex)
│   ├── snapshot_service.py     Série historique portefeuille + risque
│   ├── prediction_service.py   Orchestration ML
│   ├── analytics_service.py    Analytics avancées (Monte Carlo, MPT, XIRR)
│   ├── smart_insights_service.py  Score santé + insights
│   ├── alert_service.py        Gestion alertes
│   ├── report_service.py       Génération PDF/Excel
│   ├── email_service.py        SMTP emails
│   ├── notification_service.py In-app notifications
│   └── exchanges/              10 adapters exchange (Binance, Kraken, etc.)
├── ml/
│   ├── forecaster.py           Ensemble 7 modèles
│   ├── anomaly_detector.py     Isolation Forest + Z-score
│   ├── regime_detector.py      7 indicateurs techniques → 4 phases
│   ├── adaptive_thresholds.py  Seuils auto-calibrés
│   ├── market_context.py       Contexte marché dynamique
│   ├── drift_detector.py       Détection dérive modèles
│   ├── hyperparameter_tuner.py Optimisation hyperparamètres
│   ├── backtester.py           Walk-forward backtesting
│   └── historical_data.py      Fetcher CoinGecko + Yahoo
├── tasks/
│   ├── celery_app.py           Configuration Celery
│   ├── history_cache.py        Backfill prix historiques
│   ├── price_updates.py        Mise à jour prix périodique
│   └── alert_checker.py        Vérification alertes
├── models/                     SQLAlchemy models (User, Asset, Transaction, etc.)
├── schemas/                    Pydantic schemas (validation I/O)
└── core/
    ├── config.py               Settings (.env)
    ├── security.py             JWT + bcrypt + TOTP
    ├── database.py             AsyncSessionLocal (PostgreSQL + asyncpg)
    ├── rate_limit.py           Slowapi rate limiting
    └── symbol_map.py           CoinGecko ID mapping
```

---

## Stack ML/IA

| Composant | Technologie | Usage |
|-----------|-------------|-------|
| **Prédictions prix** | Prophet, ARIMA, XGBoost, EMA, LinReg, Mean Reversion | Ensemble pondéré MAPE |
| **Anomalies** | Isolation Forest (sklearn), Z-score | Détection spikes/drops |
| **Régime marché** | 7 indicateurs techniques | Classification 4 phases |
| **Optimisation** | scipy.optimize | Modern Portfolio Theory |
| **Monte Carlo** | numpy random | 5000 simulations |
| **Feature importance** | SHAP | Explication XGBoost |
| **Backtesting** | Walk-forward custom | MAPE, RMSE, Hit Rate |
| **Seuils adaptatifs** | Statistiques historiques | Calibration par asset |

**⚠️ Pas de LLM** dans le stack actuel. Tout est ML classique + rule-based.

---

## APIs Externes

| API | Usage | Limite Free | Auth |
|-----|-------|-------------|------|
| **CoinGecko** | Prix crypto, historique (365j max free) | 50 req/min | Optionnel (API key) |
| **Yahoo Finance** | Prix actions/ETF/crypto (illimité) | Throttled | Aucune |
| **Binance WS** | Prix temps réel crypto | N/A (WebSocket) | Aucune (public) |
| **Exchangerate-API** | Taux de change fiat | 1500 req/mois | API key |
| **10 Exchanges REST** | Sync balances/trades | Variable | API key utilisateur |

---

## Stratégie de Cache

| Couche | Stockage | TTL | Taille max | Clé |
|--------|----------|-----|-----------|-----|
| Métriques Dashboard | In-memory dict | 2 min | 200 entries | `(user_id, days)` |
| Série historique | In-memory dict | 2 min | 200 entries | `(user_id, days)` |
| Prix historiques | In-memory dict | 30 min | 500 entries | `(symbol, days)` |
| Prix crypto | Redis | 2 min | ∞ | `price:{symbol}` |
| Prix actions | Redis | 5 min | ∞ | `price:{symbol}` |
| Taux forex | Redis | 1 heure | ∞ | `forex:{pair}` |
| Prédictions ML | Redis | 1 heure | ∞ | `pred:{symbol}:{hash}` |
| IDs CoinGecko | Redis | 7 jours | ∞ | `cg_id:{symbol}` |
| Historique backfill | PostgreSQL | Permanent | 6220+ rows | `asset_price_history` |

---

## Matrice de Priorité

| # | Module | Avancement | Données réelles | Suggestion amélioration |
|---|--------|-----------|----------------|------------------------|
| 1 | Dashboard | ✅ 100% | ✅ 6220 prix | **Done** — fiabilité validée |
| 2 | Portefeuille | ✅ 100% | ✅ | **Done** |
| 3 | Transactions | ✅ 100% | ✅ | **Done** |
| 4 | Exchanges | ✅ 100% | ✅ | **Done** |
| 5 | Analyses | ✅ 100% | ✅ | **Done** |
| 6 | Projections | ✅ 100% | ✅ 7 modèles ML | Affiner accuracy des modèles |
| 7 | Paramètres | ✅ 100% | N/A | **Done** |
| 8 | Admin | ✅ 100% | N/A | **Done** |
| 9 | Smart Insights | ✅ 90% | ✅ Rule-based | Ajouter LLM pour insights textuels |
| 10 | Simulations | ✅ 90% | ✅ | Peaufiner UX (charts interactifs) |
| 11 | Alertes | ✅ 90% | ✅ | Push notifications (PWA) |
| 12 | Insights | ✅ 85% | ✅ | Enrichir tax-loss harvesting |
| 13 | Objectifs | ✅ 85% | ✅ | Charts progression, milestones |
| 14 | Journal | ✅ 85% | ✅ | Rich text editor (Markdown/WYSIWYG) |
| 15 | Calendrier | ✅ 85% | ✅ | Vue calendrier grille visuelle |
| 16 | Rapports | ✅ 80% | ✅ | Enrichir templates PDF, ajouter types |

**Conclusion** : Tous les 16 modules sont fonctionnels avec données réelles. Aucun n'est en mode placeholder.
