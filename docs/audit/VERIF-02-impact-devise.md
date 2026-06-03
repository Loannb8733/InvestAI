# VERIF-02 — Quantification de l'impact des bugs devise (FIN-01 / FIN-02)

> **Statut** : terminé · **Mode** : lecture seule, données **100 % synthétiques** (aucune copie de la DB prod)
> **Outils** : `~/envs/datascience` (scipy 1.17.0, numpy 2.4.2) · script `/tmp/verif02.py`
> **Méthode** : réplication **verbatim** du solveur `_xirr` (`analytics_service.py:292-316`) et des deux
> chemins de calcul de coût (`metrics_service.py:650-677`, `analytics_service.py:1564-1644`).

---

## 1. Objet

Mesurer l'erreur réelle, en euros et en points de pourcentage, des deux bugs devise
déjà identifiés dans l'audit financier :

- **FIN-01** — `metrics_service` traite le `price` (en USDT/USD) comme s'il était déjà en EUR
  pour le coût de base, parce que `sync_exchanges` force `currency="EUR"` et ne renseigne
  jamais `conversion_rate`.
- **FIN-02** — `compute_xirr` convertit **tous** les flux avec un **unique** taux `USD→EUR`
  récupéré au moment du calcul (≈ 0,92), ignore `tx.currency`, compte les transferts internes
  comme des flux de trésorerie, et ignore dividendes/intérêts.

---

## 2. Scénario synthétique

Utilisateur crypto mixte, devise de préférence **EUR**. `fx` = EUR par USD à la date du trade.

| Type | Actif | Qté | Prix | Devise réelle | fx trade | Frais | Date |
|---|---|---|---|---|---|---|---|
| BUY | BTC | 0,5 | 60 000 | USD (USDT) | 0,915 | 30 | 2024-01-15 |
| BUY | BTC | 0,2 | 55 000 | **EUR (SEPA)** | 1,000 | 20 | 2024-02-01 |
| BUY | ETH | 5 | 3 000 | USD (USDT) | 0,925 | 15 | 2024-03-10 |
| BUY | SOL | 50 | 120 | USD (USDT) | 0,925 | 6 | 2024-05-20 |
| TRANSFER_OUT | BTC | 0,3 | 65 000 | USD | 0,920 | 0 | 2024-06-01 |
| TRANSFER_IN | BTC | 0,3 | 65 000 | USD | 0,920 | 0 | 2024-06-02 |
| STAKING_REWARD | SOL | 2 | 140 | USD | 0,920 | 0 | 2024-07-01 |
| DIVIDEND (intérêt crowdfunding) | — | — | 100 | EUR | 1,000 | 0 | 2024-08-01 |

Prix live (USD) : BTC 95 000 · ETH 3 500 · SOL 150 · `fx_now = 0,92`.
Holdings nets (le transfert out/in s'annule) : BTC 0,7 · ETH 5 · SOL 52.
**Valeur actuelle correcte : 84 456,00 €.**

---

## 3. Résultats

### FIN-01 — Coût de base & P&L (carte « patrimoine / plus-value »)

| Mesure | Affiché (buggé) | Vrai | Écart |
|---|---|---|---|
| Montant investi | **62 071,00 €** | 57 941,88 € | **+7,13 %** sur-évalué |
| Plus-value (P&L) | 22 385,00 € (**+36,06 %**) | 26 514,12 € (**+45,76 %**) | **−4 129,12 €** sous-estimé |
| Erreur en points | — | — | **+9,70 pts** |

> **Lecture honnête** : l'erreur de coût de base n'est **pas** un uniforme 8,7 % comme on
> pourrait le croire — elle vaut +7,13 % **ici** parce qu'un achat sur huit est en EUR réel
> (non affecté). Sur un portefeuille **100 % achats USDT**, l'erreur monte à exactement
> **+8,70 %** (= 1/0,92 − 1). Le chiffre dépend de la proportion d'achats fiat vs exchange.

### FIN-02 — XIRR (performance annualisée)

| Mesure | Affiché (buggé) | Corrigé | Écart |
|---|---|---|---|
| XIRR | **+18,75 %** | +18,08 % | **−0,67 pts** |

> **Lecture honnête — et contre-intuitive** : l'impact du bug XIRR est **faible** (−0,67 pt)
> sur ce portefeuille, et il faut le dire clairement plutôt que de le gonfler.
> La raison est mathématique : **le TRI est invariant par changement d'échelle**. Multiplier
> *tous* les flux par 0,92 ne change rien au TRI. Or les achats en USDT (la majorité) sont
> précisément ceux pour lesquels « ×0,92 » est ≈ correct. L'erreur résiduelle du XIRR ne vient
> donc **que** des cas marginaux :
> - l'achat réellement en **EUR** que le code multiplie à tort par 0,92 (sous-estime l'investi) ;
> - les **transferts internes** comptés comme flux (décalage de timing) ;
> - le **dividende/intérêt** de 100 € ignoré.
>
> **Conclusion** : FIN-02 est un vrai bug de correction (sémantiquement faux : il ignore
> `tx.currency`), mais son impact chiffré sur le % de performance est **secondaire** comparé
> à FIN-01. Le backlog doit refléter cette hiérarchie : **FIN-01 > FIN-02** en priorité d'effet visible.

### Incohérence inter-vues (le constat le plus net)

Pour **les mêmes achats**, deux écrans donnent deux bases d'investissement différentes :

| Vue | Base investie (achats) |
|---|---|
| Carte P&L (`metrics`, price = EUR) | 62 071,00 € |
| Calcul XIRR (`analytics`, price × 0,92) | 57 105,32 € |
| **Désaccord** | **+8,70 %** |

> La carte « plus-value » et le « % de performance » **ne partent pas du même montant investi**.
> C'est l'incohérence la plus facile à constater pour un utilisateur attentif (et la plus
> dommageable pour la confiance dans une app qui suit de l'argent réel).

### Sensibilité au forex (FIN-05, code sous FIN-02)

`fx_now` est un fallback codé en dur. En le faisant varier, le XIRR affiché bouge de **8,4 pts** :

| fx_now | XIRR affiché |
|---|---|
| 0,85 | +22,90 % |
| 0,90 | +19,89 % |
| 0,92 | +18,75 % |
| 0,95 | +17,11 % |
| 1,00 | +14,53 % |

> Un simple décalage du taux de change (ou un fallback figé pendant que l'EUR/USD bouge) peut
> faire varier la performance annualisée affichée de plusieurs points. **Ceci** est un risque
> plus grand que le bug XIRR lui-même.

---

## 4. Synthèse & priorisation (mise à jour du backlog)

| Bug | Impact mesuré | Visibilité utilisateur | Priorité confirmée |
|---|---|---|---|
| **FIN-01** coût de base | +7 % à +8,7 % de coût ; **P&L sous-estimé ~10 pts** | Élevée (carte principale) | **P0 — confirmée** |
| **Incohérence inter-vues** | 8,70 % d'écart sur la même donnée | Élevée (deux écrans qui se contredisent) | **P0 — à traiter avec FIN-01** |
| **FIN-05** forex hardcodé | swing XIRR jusqu'à **8,4 pts** | Moyenne-élevée (perf bouge sans raison) | **P1 — relevée** (sous-estimée à l'audit) |
| **FIN-02** XIRR multi-devise | **−0,67 pt** sur ce cas | Faible-moyenne | **P1 — maintenue mais dé-priorisée vs FIN-01** |

### Désaccord assumé avec l'intuition initiale
L'audit (et moi-même) supposions que FIN-02 (XIRR) était aussi impactant que FIN-01.
**La mesure dit le contraire** : l'invariance d'échelle du TRI rend le XIRR largement
auto-corrigé pour les trades USDT. Je corrige donc la hiérarchie : **le vrai problème
quantifié, c'est la base de coût (FIN-01) et l'incohérence entre les deux écrans**, pas le
solveur XIRR. La correction de FIN-02 reste nécessaire pour la *justesse sémantique*
(dividendes ignorés, transferts comptés) mais pas pour « gagner des points » de précision.

---

## 5. Limites de cette quantification

- Un **seul** scénario synthétique : les chiffres exacts (7,13 %, −0,67 pt) dépendent du mix
  fiat/exchange, des dates et de la volatilité de l'EUR/USD. Les **bornes** (8,7 % pur-USDT,
  8,4 pts de swing forex) sont elles robustes.
- Pas de slippage, pas de frais en devise tierce non-EUR/USD, pas de ventes partielles ici.
- Replique l'arithmétique du code, **pas** l'I/O (DB, prix live) — volontaire, pour rester
  hors-prod et déterministe.
- Le script `/tmp/verif02.py` est jetable (hors repo) ; il peut être recréé depuis ce rapport.
```
