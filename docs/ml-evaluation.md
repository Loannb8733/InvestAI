# Évaluation du moteur de prévision

Banc reproductible : `backend/scripts/ml_backtest/` (`backtest.py`, `analyze.py`, données figées
`data/binance_daily.json`).

## Méthode

- **Données** : clôtures quotidiennes publiques Binance (paires USDT) de BTC, ETH, SOL, XRP, BNB et ADA, du
  1er janvier 2021 au 15 novembre 2026, figées dans le dépôt pour que chaque exécution compare les mêmes séries.
- **Protocole** : walk-forward. Pour chaque paire, 34 origines espacées de 21 jours (du 22/11/2024 au 16/10/2026),
  soit 204 prévisions. À chaque origine, le `PriceForecaster` de production reçoit les 365 jours précédents (comme
  `HISTORY_DAYS` en production), les volumes en devise de cotation et, hors BTC, le cours du BTC ; il prévoit
  30 jours, comparés aux clôtures réelles.
- **Référence** : la prévision naïve « prix constant » (le dernier cours), qu'un modèle doit battre pour être utile.
- **Mesures** : erreur absolue en pourcentage (MAPE) à 1, 7 et 30 jours, part des origines où l'ensemble bat la
  référence, couverture et largeur de l'intervalle annoncé à 95 %. Erreur médiane et maximale par modèle.
- **Isolation** : ni base ni Redis (aucun cache), hyperparamètres par défaut, une graine fixe par modèle.

Reproduire (depuis `backend/`) :

```bash
cd scripts/ml_backtest
BT_BACKEND=~/projects/InvestAI-baseline/backend python backtest.py ~/pe-bt/before
python backtest.py ~/pe-bt/after
python analyze.py avant=~/pe-bt/before/results.jsonl apres=~/pe-bt/after/results.jsonl
```

`BT_BACKEND` pointe vers le code évalué (ici une worktree sur le tag `pe-2627-baseline` pour l'état initial).

## Résultats (backtest du 16/11/2026)

« Avant » : code du tag `pe-2627-baseline`. « Après » : branche `fix/ml-prod`. Les étapes intermédiaires isolent
l'effet de chaque correction (ablation).

| Étape | Changements |
|---|---|
| 1 | Linear recalé sur le dernier prix (pente des 90 derniers jours) ; XGBoost prédit des rendements logarithmiques bornés au lieu de niveaux de prix |
| 2 | Tendances amorties (φ = 0,9) pour Linear et EMA ; Prophet et EMA partent du dernier prix ; XGBoost amorti plus fort ; prévision naïve ajoutée à l'ensemble |
| Après | Un modèle dont l'erreur de backtest ne bat pas celle de la prévision naïve sur la même série est écarté de l'ensemble |

### Ensemble

| Horizon | Mesure | Avant | Étape 1 | Étape 2 | Après |
|---|---|---:|---:|---:|---:|
| 1 j | MAPE (naïf : 1,50 %) | 3,15 % | 1,80 % | 1,53 % | 1,56 % |
| 1 j | Erreur médiane (naïf : 1,01 %) | 1,98 % | 1,14 % | 1,16 % | 1,05 % |
| 1 j | Largeur de l'intervalle « 95 % » | 56,4 % | 20,8 % | 18,4 % | 18,0 % |
| 7 j | MAPE (naïf : 6,10 %) | 7,02 % | 6,51 % | 6,41 % | 6,23 % |
| 7 j | Erreur médiane (naïf : 4,13 %) | 5,23 % | 4,84 % | 4,47 % | 4,29 % |
| 7 j | Couverture de l'intervalle « 95 % » | 100 % | 96 % | 96 % | 97 % |
| 7 j | Largeur de l'intervalle « 95 % » | 103,8 % | 48,7 % | 46,2 % | 46,1 % |
| 30 j | MAPE (naïf : 15,68 %) | 16,61 % | 17,13 % | 16,32 % | 15,72 % |
| 30 j | Erreur médiane (naïf : 11,78 %) | 12,88 % | 12,94 % | 12,46 % | 11,85 % |
| 30 j | Couverture de l'intervalle « 95 % » | 100 % | 97 % | 95 % | 95 % |
| 30 j | Largeur de l'intervalle « 95 % » | 154,3 % | 108,0 % | 96,6 % | 96,1 % |

### Modèles pris seuls (MAPE, erreur maximale)

| Modèle | 1 j avant | 1 j après | 7 j avant | 7 j après | 30 j avant | 30 j après |
|---|---:|---:|---:|---:|---:|---:|
| Linear | 22,6 % (85 %) | 1,6 % (10 %) | 24,1 % (90 %) | 6,8 % (38 %) | 29,7 % (109 %) | 17,1 % (64 %) |
| XGBoost | 7,6 % (68 %) | 1,7 % (7 %) | 31,9 % (287 %) | 6,9 % (40 %) | 16,4 % (107 %) | 16,9 % (83 %) |
| Prophet | 5,6 % (41 %) | 1,8 % (11 %) | 10,6 % (106 %) | 8,8 % (82 %) | 25,0 % (202 %) | 25,8 % (210 %) |
| EMA | 2,8 % (17 %) | 1,8 % (7 %) | 8,7 % (44 %) | 8,6 % (44 %) | 38,6 % (229 %) | 20,3 % (84 %) |
| ARIMA | 1,6 % (9 %) | inchangé | 6,3 % (36 %) | inchangé | 16,8 % (91 %) | inchangé |
| MeanReversion | 1,5 % (9 %) | inchangé | 6,4 % (33 %) | inchangé | 16,9 % (85 %) | inchangé |
| Naïf | 1,5 % (9 %) | — | 6,1 % (36 %) | — | 15,7 % (68 %) | — |

### Lecture

- **Avant**, l'ensemble faisait moins bien que la prévision « prix constant » à tous les horizons, et ses
  intervalles « 95 % » couvraient tout (100 %) parce qu'ils faisaient une à une fois et demie le prix.
- Les deux défauts identifiés expliquaient l'essentiel : Linear ne partait pas du dernier prix (19,5 % d'erreur
  médiane dès le premier jour) et XGBoost, qui prédisait des niveaux de prix, ne savait pas sortir de la plage
  vue à l'entraînement (jusqu'à 287 % d'erreur). Prophet et EMA avaient le même défaut de point de départ.
- **Après**, l'ensemble rejoint presque la prévision naïve (0,04 à 0,13 point de MAPE au-dessus, 0,04 à 0,16 point
  d'erreur médiane au-dessus), sans modèle qui s'emballe, avec des intervalles calibrés (95 à 97 % de couverture
  observée) deux à trois fois plus étroits.
- **Il ne bat pas la marche aléatoire.** Sur des cours quotidiens de cryptomonnaies, c'est le résultat attendu :
  aucun des six modèles ne la bat en moyenne. Le filtre de compétence en tire la conséquence : dans 54 prévisions
  sur 204, aucun modèle ne battait le naïf en backtest sur l'actif concerné, et la prévision affichée est plate
  (« Naive : 100 % »). Modèles retenus sur 204 prévisions : Linear 90, XGBoost 59, MeanReversion 50, Prophet 48,
  ARIMA 39, EMA 33.
- La « direction juste » n'est pas une mesure de qualité ici : une prévision égale au dernier prix est comptée
  comme une baisse, et 61 % des origines sont suivies d'une baisse.
