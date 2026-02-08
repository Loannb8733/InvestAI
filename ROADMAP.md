# InvestAI — Analyse & Roadmap

## Audit technique (Data Analyst / AI Engineer Senior)

### ML/AI — Score : 7.5/10

**Ce qui est solide :**
- Ensemble de 5 modèles (Prophet, ARIMA, XGBoost, EMA, Linear Regression) avec pondération par backtest MAPE
- Feature engineering : RSI 14j, volatilité 7j, lagged returns, ratio prix/SMA20
- ARIMA auto-sélection par AIC, scaling numérique pour petits prix
- Intervalles de confiance sur chaque modèle
- Anomaly detection : Isolation Forest + Z-score (seuils adaptatifs 2.5σ crypto, 3σ actions)

**Analytics de niveau institutionnel :**
- Sharpe, Sortino, Calmar — formules textbook
- VaR historique + paramétrique, CVaR / Expected Shortfall
- Max drawdown avec dates peak/trough
- Monte Carlo avec décomposition de Cholesky
- Optimisation Markowitz (SLSQP, contraintes long-only)
- Stress testing sur 5 scénarios historiques (COVID, crypto winter, 2008, rate shock, flash crash)
- XIRR par Newton-Raphson + fallback Brentq
- Beta/Alpha vs benchmarks (BTC crypto, SPY actions)

**Ce qui manque (MLOps) :**
- Pas de persistence/cache des modèles fitted → refittés à chaque requête
- Pas de cache features (RSI, volatilité recalculés à chaque appel)
- Hyperparamètres hardcodés (XGBoost: n_estimators=100, max_depth=4) jamais optimisés
- Pas de retraining pipeline → modèles ne s'adaptent pas aux nouvelles données
- Pas de monitoring drift → impossible de savoir si les prédictions se dégradent
- Pas de tests unitaires ML
- Grille ARIMA trop petite (p=0..3, q=0..2) → devrait utiliser pmdarima.auto_arima
- Taux sans risque hardcodé → devrait fetch ECB ESTER ou OAT 10Y
- Monte Carlo assume log-normal → devrait tester Student-t (fat tails)

**Priorités MLOps :**
1. Cache Redis des modèles fitted (24h TTL)
2. Optuna pour hyperparams XGBoost
3. Walk-forward backtesting rigoureux avec train/test split
4. Log les MAPE en base pour monitorer la qualité
5. SHAP values sur XGBoost pour expliquer les prédictions

---

## Audit fonctionnel (Analyste Financier)

### 25 features production-ready

1. Dashboard complet (patrimoine, P&L réalisé/latent, allocation, benchmarks)
2. Multi-portfolio, multi-exchange (Binance, Kraken, Crypto.com)
3. Suivi crypto/actions/ETF avec prix live (CoinGecko, Yahoo Finance)
4. Fiscalité française 2086 avec PMP global (mieux que Finary)
5. Simulation FIRE (nombre, années, revenu passif, projection)
6. Simulation DCA (Monte Carlo, prix moyen, rendement)
7. Simulation projections (nominal vs réel inflation)
8. Simulation what-if (chocs de prix par actif)
9. Alertes prix/performance (above/below, % change, daily change, portfolio value)
10. Calendrier financier (dividendes, loyers, échéances, récurrence)
11. Objectifs financiers (cible, progression, deadline, sync portfolio)
12. Reports PDF/Excel (performance + fiscal 2086)
13. Matrice de corrélation avec heatmap
14. Diversification (HHI, recommandations, score composite)
15. Optimisation MPT Markowitz (max Sharpe, poids optimaux)
16. Stress testing (5 scénarios historiques)
17. Monte Carlo (1000+ simulations, percentiles P5-P95)
18. XIRR (rendement pondéré dans le temps)
19. Benchmark comparison (BTC/SPY/MSCI World, base 100)
20. P&L breakdown (réalisé vs latent, fees)
21. Journal d'investissement (notes par actif)
22. Import/export CSV
23. Cash management (fiat, stablecoins, balances par exchange)
24. Intégration exchanges (API keys chiffrées Fernet)
25. Dashboard customisable (drag-and-drop, hide/show widgets)

### Ce qui manque vs Finary

| Feature | Importance | Difficulté |
|---------|-----------|------------|
| Agrégation bancaire (Open Banking) | Critique | Haute — Budget Insight, Plaid |
| Suivi dettes/crédits (immo, conso) | Haute | Moyenne — modèle + CRUD |
| Assurance-vie / PER | Haute | Moyenne — types d'actifs + rendement fonds euros |
| Valorisation immobilière auto | Haute | Moyenne — API DVF/Notaires |
| Métaux précieux (or, argent) | Moyenne | Faible — source de prix |
| Crowdfunding (Anaxago, Fundimmo) | Moyenne | Faible — actif custom |
| Stock options / RSU | Moyenne | Moyenne — vesting schedule + valorisation |
| Staking APY tracking | Moyenne | Faible — transactions staking déjà là |
| Rebalancing automatique | Basse | Moyenne — allocation vs cible |

---

## Positionnement stratégique

**Ne pas copier Finary.** Finary est fort sur la largeur (tous les actifs, banques, assurances). InvestAI ne les rattrapera pas en solo.

**Se positionner comme plateforme analytics-first** pour investisseurs actifs crypto/actions qui veulent des outils quantitatifs que Finary n'offre pas.

### 3 différenciateurs clés

**1. L'IA comme vrai USP**
Finary n'a pas de prédictions ML, pas de Monte Carlo, pas d'optimisation Markowitz, pas de stress testing. InvestAI oui. Mais il faut que ce soit visible et utile :
- Alertes intelligentes ("ton portfolio a un Sharpe de 0.3, voici comment l'améliorer à 0.8")
- Suggestions de rebalancing basées sur l'optimisation MPT
- Détection d'anomalies proactive ("BTC -15% en 2h, ta perte latente est de X€")

**2. Fiscalité avancée**
La déclaration 2086 est déjà meilleure que Finary. Pousser plus loin :
- Simulation d'impact fiscal avant vente ("si tu vends maintenant → X€ de flat tax")
- Tax-loss harvesting ("vends cet actif en moins-value pour compenser tes plus-values")
- Optimisation holding period ("attends 3 mois pour passer en long terme")

**3. Open-source / Self-hosted**
Finary est SaaS propriétaire. Publier InvestAI en open-source touche une niche de gens qui veulent garder le contrôle de leurs données financières. Argument fort dans la communauté crypto.

---

## Scores globaux

| Aspect | Score |
|--------|-------|
| Code ML/Analytics | 7.5/10 |
| Features financières | 8/10 |
| Largeur asset classes | 5/10 |
| UX/Frontend | 7/10 |
| Compétitivité vs Finary | 6/10 |
