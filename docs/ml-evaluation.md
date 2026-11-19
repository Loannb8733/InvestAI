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

## Recherche systématique sous le naïf (19/11/2026)

Demande : faire au minimum sur chaque « % d'erreur », sans jamais faire pire que la prévision naïve, sur chaque
horizon et chaque actif, hors échantillon.

**Limite à connaître.** Un MAPE de 0 % suppose de connaître le cours futur. Sur des cryptos, l'essentiel du
mouvement quotidien est imprévisible : le naïf se trompe en moyenne de 2,4 à 3,2 % à 1 jour et de 14 à 18 % à
30 jours. Aucune méthode ne peut descendre près de zéro. Les gains ci-dessous sont réels et significatifs, mais
ils restent de quelques points.

### Protocole

| Jeu | Actifs | Origines | Rôle |
|---|---|---|---|
| Validation | BTC, ETH, SOL, XRP, BNB, ADA | une par jour, janv. 2022 → nov. 2024, environ 6 300 prévisions par horizon | tous les choix |
| Banc historique | les mêmes 6 | une par jour, nov. 2024 → nov. 2026, environ 4 300 | contrôle |
| Test 1 | DOGE, LTC, LINK, AVAX, DOT, TRX | idem | contrôle, déjà vu pour cette famille de méthodes |
| **Test final 2** | BCH, ETC, XLM, ATOM, NEAR, AAVE | idem | **figé avant les choix, évalué une seule fois** |

Le test 1 a servi une première fois (pas de 21 jours, 204 prévisions) à mesurer la version « naïf pur ». J'y ai
vu le bon comportement d'une variante corrigée, ce qui aurait pu orienter la suite. J'ai donc figé un second test
(`data/binance_daily_test2.json`) avant de choisir les réglages, et il n'a été évalué qu'une fois, avec le code de
production. Chaque gain est jugé par un test de Diebold-Mariano sur l'écart d'erreur relative avec le naïf, avec
un écart-type de Newey-West pour les horizons qui se chevauchent. Un DM inférieur à −2 signifie un gain
significatif.

### Ce qui a été testé sur la validation

| Famille | Résultat | Script |
|---|---|---|
| Combinaisons des 7 modèles (ensemble, médiane, moyenne) rétrécies vers le naïf | λ optimal = 0 : toute part donnée aux modèles augmente l'erreur | `combine.py` |
| Signaux de marché : momentum, retour à la moyenne, volatilité, volumes, avance de BTC, jour de la semaine | corrélations avec le rendement futur sous 0,1 en valeur absolue, sauf la volatilité à 30 j (−0,18) | `research.py` |
| Modèles appris en walk-forward sur ces signaux (ridge, Huber, boosting en erreur absolue), réentraînés tous les 30 jours sur le passé seulement | **pires que le naïf** et significativement (DM de +2 à +5) : ils apprennent du bruit | `research.py` |
| Correction propre au MAPE, p0 · exp(−κ(h) · σ² · h), fenêtres de volatilité de 30, 90, 180 et 365 j | **meilleure que le naïf sur chaque actif et chaque horizon**, DM de −2 à −5 | `research_shift.py` |
| Intervalles : quantiles empiriques, volatilité EWMA, volatilité × √h | la volatilité × √h est la plus étroite pour 95 % de couverture | `intervals.py`, `research_shift.py` |

La correction vient de la forme même du MAPE. L'erreur relative pénalise davantage une prévision trop haute
qu'une prévision trop basse du même écart, puisque l'erreur est divisée par le cours réalisé. Pour des
rendements log-normaux, la prévision qui la minimise est donc légèrement **sous** le dernier cours, d'autant plus
que la volatilité et l'horizon sont grands. Ce n'est pas une prévision de baisse : le biais moyen de la prévision
est négatif par construction.

Règle de choix, fixée avant tout contrôle : pour chaque horizon, le κ au MAPE le plus bas parmi ceux qui battent
le naïf sur chaque actif avec un DM < −2. La fenêtre de 365 jours donne le MAPE le plus bas et les intervalles
les plus étroits. Réglages retenus (`app/ml/forecasting/floor.py`) :
- **κ(h) = 0,6 + 0,3 · min(1, ln h / ln 7)**, soit 0,6 à 1 j et 0,9 dès 7 j ;
- **σ** : volatilité quotidienne sur 365 j ;
- **intervalle** : p0 · exp(± 1,96 · m(h) · σ · √h), avec **m(h) = 0,978 + 0,020 · ln h**.

Les modèles tournent toujours et restent listés avec leurs poids. La trajectoire servie est la prévision corrigée.

### Test final 2 : 6 actifs vierges, code de production, évalué une seule fois

| Horizon | Prévisions | MAPE naïf | MAPE servi | Gain | DM | Actifs ≤ naïf | Couverture | Largeur |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 j | 4 338 | 3,18 % | **3,17 %** | −0,3 % | −4,3 | 6/6 | 94,4 % | 17,6 % |
| 7 j | 4 302 | 8,47 % | **8,23 %** | −2,8 % | −6,0 | 6/6 | 96,0 % | 48,9 % |
| 30 j | 4 164 | 17,97 % | **16,09 %** | −10,5 % | −5,0 | 6/6 | 97,7 % | 108,2 % |

| Actif | 1 j naïf → servi | 7 j naïf → servi | 30 j naïf → servi |
|---|---:|---:|---:|
| AAVE | 3,63 → 3,62 % | 9,67 → 9,52 % | 20,19 → 18,10 % |
| ATOM | 2,96 → 2,95 % | 7,93 → 7,66 % | 16,11 → 14,17 % |
| BCH | 2,72 → 2,72 % | 7,49 → 7,41 % | 16,12 → 15,81 % |
| ETC | 2,77 → 2,76 % | 6,78 → 6,54 % | 14,83 → 12,93 % |
| NEAR | 3,92 → 3,91 % | 10,65 → 10,35 % | 23,65 → 21,17 % |
| XLM | 3,11 → 3,10 % | 8,30 → 7,92 % | 16,92 → 14,35 % |

### Contrôles, même code

| Jeu | 1 j naïf → servi | 7 j naïf → servi | 30 j naïf → servi | Actifs ≤ naïf (1/7/30 j) | Couverture 1/7/30 j |
|---|---:|---:|---:|---:|---:|
| Validation | 2,67 → 2,66 % | 7,46 → 7,36 % | 16,28 → 15,44 % | 6/6/6 | 95,0 / 95,1 / 95,5 % |
| Banc historique | 2,44 → 2,43 % | 6,63 → 6,51 % | 14,54 → 13,83 % | 5/6/5 | 95,0 / 95,6 / 96,7 % |
| Test 1 | 2,77 → 2,76 % | 7,37 → 7,20 % | 16,25 → 14,98 % | 5/6/5 | 95,2 / 96,7 / 99,4 % |

Exceptions : sur le banc, BNB à 30 j (10,25 → 10,28 %) et un actif à 1 j (écart de 0,09 %). Sur le test 1, TRX
à 7 j (3,60 → 3,71 %) et à 30 j (6,55 → 7,23 %) : c'est l'actif le moins volatil, et il a monté sur la période.
Le plancher « jamais pire sur chaque actif » tient donc sur la validation et sur le test final 2, mais pas
toujours ailleurs. Il n'est pas garanti hors échantillon.

Pour mémoire, l'ensemble de modèles d'avant (pas de 21 jours, test 1) faisait 2,36 / 8,12 / 19,08 %, contre
2,32 / 7,96 / 18,42 % pour le naïf.

### Reproduire

`python research.py`, `python research_shift.py valider`, puis
`python evaluate_floor.py binance_daily_test2.json 2024-11-22 2026-11-16` (code de production en origines
quotidiennes). Le banc à 21 jours (`backtest.py`, `report.py`) reste disponible, avec `BT_SKIP` et `BT_DATA` pour
la validation et les tests.

### Modèle de fondation : Chronos-Bolt

`amazon/chronos-bolt-small` (chronos-forecasting 2.3.2), utilisé sans réentraînement, avec un contexte des 512
derniers cours. Il est évalué sur la validation quotidienne (`chronos_eval.py`, environnement à part
`~/envs/chronos`), contre le naïf et contre la correction retenue :

| Horizon | Prévisions | Naïf | Correction retenue | Chronos médiane | Chronos point MAPE | DM médiane / naïf | Pire actif / naïf |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 j | 5 448 | 2,514 % | **2,512 %** | 3,054 % | 3,162 % | +20,7 | 1,39 |
| 7 j | 5 412 | 7,017 % | **6,996 %** | 7,459 % | 7,796 % | +5,8 | 1,19 |
| 30 j | 5 274 | 14,489 % | **14,274 %** | 15,643 % | 16,303 % | +3,5 | 1,18 |

Chronos est significativement moins bon que le naïf à chaque horizon : +21 % d'erreur à 1 jour. Il projette des
motifs appris sur d'autres séries, alors que les cours crypto quotidiens sont proches d'une marche aléatoire.
Écarté sur la validation, il n'a été évalué sur aucun jeu de test. Les variantes plus grosses (chronos-bolt-base,
Chronos-2) n'ont pas été téléchargées.
