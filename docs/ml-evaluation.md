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

## Plancher naïf et intervalles calibrés (19/11/2026)

Demande : sur chaque « % d'erreur », faire au minimum, et ne jamais faire pire que la prévision naïve (dernier
cours), sur chaque horizon et chaque actif, hors échantillon.

### Protocole

Les réglages ont été fixés sur une période de validation, puis appliqués sans retouche au banc historique et à un
test final. Aucun réglage n'a été fait sur les données de test.

| Jeu | Actifs | Origines (pas de 21 j) | Rôle |
|---|---|---|---|
| Validation | BTC, ETH, SOL, XRP, BNB, ADA | janv. 2022 → oct. 2024, 300 prévisions | tous les choix |
| Banc historique | les mêmes 6 | nov. 2024 → oct. 2026, 204 prévisions | contrôle, déjà vu le 16/11 |
| Test final | DOGE, LTC, LINK, AVAX, DOT, TRX | nov. 2024 → oct. 2026, 204 prévisions | évalué une seule fois, code figé |

Le test final a ses propres données figées (`data/binance_daily_test.json`). Pour le reproduire :
`BT_DATA=binance_daily_test.json BT_SYMBOLS=DOGEUSDT,LTCUSDT,LINKUSDT,AVAXUSDT,DOTUSDT,TRXUSDT python backtest.py <dossier>`,
puis `python report.py <dossier>/results.jsonl --data binance_daily_test.json`. La validation se lance avec
`BT_SKIP=34 BT_ORIGINS=50`.

### Ce que la validation a décidé

Les scripts `combine.py`, `tune.py`, `tune2.py` et `intervals.py` testent les combinaisons sur les prévisions
enregistrées, sans relancer les modèles.

- **Rétrécissement vers le naïf**, prévision = naïf + λ × (combinaison − naïf), avec pour combinaison l'ensemble,
  la médiane ou la moyenne des modèles. Le meilleur réglage est **λ = 0** : toute part donnée aux modèles augmente
  l'erreur. La prévision ponctuelle servie est donc le dernier cours.
- **Correction propre au MAPE**, p0 · exp(−κ · σ² · h). C'est la prévision qui minimise l'erreur relative attendue
  pour des rendements log-normaux. Elle baisse le MAPE global à 30 jours de 16,26 % à 15,70 %, mais dégrade au
  moins un actif de 0,2 à 1,5 %, aussi bien avec un κ fixe qu'avec un κ décidé actif par actif sur son année
  passée. Elle est donc **désactivée** (`MAPE_SHIFT_PER_LOG_DAY = 0`). La variante B ci-dessous, avec
  κ(h) = 0,15 · ln h, est mesurée pour information. Contrepartie : elle rend la prévision prudente, avec un biais
  moyen de −1 à −3 % à 30 jours.
- **Intervalles** : p0 · exp(± 1,96 · m(h) · σ · √h), où σ est la volatilité quotidienne de l'année passée et
  m(h) = 0,612 + 0,170 · ln h, ajusté pour couvrir 95 % à chaque horizon. C'est la méthode la plus étroite à
  couverture égale, devant les quantiles empiriques (147 % de largeur à 30 j contre 115 %) et la volatilité
  récente EWMA.

Code : `app/ml/forecasting/floor.py`, appliqué à la sortie de `PriceForecaster.ensemble_forecast`. Les modèles
tournent toujours et restent listés avec leurs poids, et leurs écarts restent signalés.

### Test final : 204 prévisions, 6 actifs jamais utilisés

« Avant » : le code de `main` à 11c4c27. « Après » : le plancher. Le code de production a tourné sur ce test, et son
résultat est identique au recalcul (écart relatif maximal de 1×10⁻⁷).

| Horizon | MAPE naïf | MAPE avant | MAPE après | Variante B (non retenue) | Couverture avant | Couverture après | Largeur avant | Largeur après |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 j | 2,32 % | 2,36 % | **2,32 %** | 2,32 % | 98 % | 91 % | 20,7 % | 10,3 % |
| 7 j | 7,96 % | 8,12 % | **7,96 %** | 7,83 % | 95 % | 94 % | 51,9 % | 42,2 % |
| 30 j | 18,42 % | 19,08 % | **18,42 %** | 17,17 % | 98 % | 100 % | 110,0 % | 115,6 % |

| Actif | MAPE 1 j avant → après | MAPE 7 j avant → après | MAPE 30 j avant → après | Après ≤ naïf partout |
|---|---:|---:|---:|:---:|
| AVAX | 2,84 → 2,79 % | 9,86 → 9,20 % | 22,96 → 22,56 % | oui |
| DOGE | 2,75 → 2,60 % | 8,95 → 8,74 % | 22,12 → 21,71 % | oui |
| DOT | 3,25 → 3,23 % | 9,62 → 10,01 % | 21,99 → 21,55 % | oui |
| LINK | 2,14 → 2,18 % | 9,36 → 8,82 % | 22,42 → 20,94 % | oui |
| LTC | 2,13 → 2,08 % | 6,65 → 7,02 % | 16,39 → 15,63 % | oui |
| TRX | 1,05 → 1,01 % | 4,27 → 3,95 % | 8,60 → 8,10 % | oui |

Le MAPE « après » est égal à celui du naïf par construction. Sur un actif donné, il peut donc dépasser l'ancien
ensemble là où celui-ci avait battu le naïf par chance : DOT et LTC à 7 j, LINK à 1 j.

### Banc historique et validation (contrôle)

| Jeu | Horizon | MAPE naïf | MAPE avant | MAPE après | Variante B | Couverture avant → après | Largeur avant → après |
|---|---|---:|---:|---:|---:|---:|---:|
| Banc | 1 j | 1,50 % | 1,56 % | 1,50 % | 1,50 % | 100 % → 96 % | 18,0 → 8,9 % |
| Banc | 7 j | 6,10 % | 6,23 % | 6,10 % | 6,00 % | 97 % → 96 % | 46,1 → 36,5 % |
| Banc | 30 j | 15,68 % | 15,72 % | 15,68 % | 14,81 % | 95 % → 98 % | 96,1 → 99,2 % |
| Validation | 1 j | 1,55 % | 1,59 % | 1,55 % | 1,55 % | 99 % → 96 % | 18,7 → 10,1 % |
| Validation | 7 j | 7,29 % | 7,37 % | 7,29 % | 7,28 % | 96 % → 94 % | 48,4 → 41,6 % |
| Validation | 30 j | 16,26 % | 16,48 % | 16,26 % | 15,70 % | 91 % → 95 % | 101,6 → 114,8 % |

### Lecture

- **Plancher.** La prévision servie ne fait jamais pire que le naïf, sur chaque actif et chaque horizon des trois
  jeux, puisqu'elle est le naïf. Aucune méthode n'a fait mieux que le naïf **sur chaque actif** en validation.
  Le résultat annoncé est donc « égal au naïf », pas « meilleur ».
- **MAPE global.** Seule la variante B le baisse franchement : −6,8 % relatif à 30 j sur le test final, et sous le
  naïf sur chaque actif de ce test. Elle a été écartée sur la validation, où elle dégradait un actif. La
  réactiver est un choix produit (`MAPE_SHIFT_PER_LOG_DAY = 0.15`) : la prévision devient alors volontairement
  prudente.
- **Intervalles.** Ils sont nettement plus étroits à 1 et 7 jours. La couverture visée de 95 % n'est pas exacte
  hors échantillon : 91 % à 1 j et 100 % à 30 j sur le test final, contre 98 % et 98 % avant. Le multiplicateur
  m(h) a été réglé sur une période (2022-2024) dont la volatilité diffère de 2025-2026.
- **Pour un utilisateur,** la trajectoire affichée est plate. L'information utile est l'intervalle, c'est-à-dire
  la fourchette dans laquelle le cours devrait rester avec 95 % de chances.
