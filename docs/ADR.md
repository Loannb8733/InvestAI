# Architecture Decision Records (ADR)

Decisions techniques prises lors de l'audit de securite et qualite ML (mars 2026).

---

## ADR-001 : Rendement annualise — convention exp() vs lineaire

**Contexte :** La fonction `_annualized_return()` convertit des log-returns journaliers en pourcentage annuel.

**Decision :** Utiliser la formule composee `(exp(mean_daily * 365) - 1) * 100` et non la formule lineaire `mean_daily * 365 * 100`.

**Justification :**
- Les returns sont calcules comme `log(P_t / P_{t-1})` (log-returns continus)
- La conversion correcte de log-return en rendement discret est `exp(r) - 1`
- La formule lineaire sous-estime le rendement reel (36.5% vs 44.05% pour r=0.001/jour)
- Convention standard en finance quantitative (Hull, Shreve)

**Convention de jours :**
- Crypto : 365 jours (marche 24/7)
- Actions/ETF : 252 jours (jours de trading)
- Fonction `_trading_days(asset_type)` applique la bonne convention

---

## ADR-002 : XGBoost — random_state=42 pour le determinisme

**Contexte :** Sans seed fixe, XGBoost produit des resultats differents a chaque execution.

**Decision :** Fixer `random_state=42` sur tous les `XGBRegressor`.

**Fichiers :** `forecaster.py`, `hyperparameter_tuner.py`

**Justification :**
- Reproductibilite des predictions (meme donnees → meme resultat)
- Facilite le debugging et la validation des modeles
- Indispensable pour les tests de determinisme automatises
- Le choix de 42 est arbitraire mais conventionnel

---

## ADR-003 : Prophet — MAP estimation au lieu de MCMC

**Contexte :** Par defaut, Prophet utilise `mcmc_samples=300` (echantillonnage MCMC stochastique).

**Decision :** Forcer `mcmc_samples=0` pour utiliser l'estimation MAP (Maximum A Posteriori).

**Justification :**
- MAP est deterministe (meme donnees → meme modele)
- MCMC introduit du bruit aleatoire non reproductible
- Pour notre cas d'usage (previsions court-terme), MAP est suffisamment precis
- Gain de performance (~3x plus rapide)

---

## ADR-004 : Data Leakage XGBoost — train/val split pour les CI

**Contexte :** Les intervalles de confiance (CI) etaient calcules a partir des residus in-sample (modele entraine sur 100% des donnees).

**Decision :** Split 80/20 train/val. `model_val` entraine sur 80% pour calculer les residus honnetes. `model` entraine sur 100% pour les predictions finales.

**Justification :**
- Les residus in-sample sont systematiquement trop petits (overfitting)
- Produit des CI artificiellement etroits (fausse confiance)
- Les residus held-out refletent la vraie incertitude du modele
- Le modele final utilise toujours 100% des donnees pour les predictions

---

## ADR-005 : WebSocket auth par message initial

**Contexte :** Le JWT etait passe en query parameter (`?token=XXX`), visible dans les logs nginx/proxy.

**Decision :** Accepter la connexion WS d'abord, puis attendre un message `{"action": "auth", "token": "..."}` avec timeout 10s.

**Justification :**
- Les query params sont logges par defaut par les reverse proxies
- Un JWT dans les logs = fuite de credentials
- L'auth par message est invisible dans les logs serveur
- Timeout de 10s empeche les connexions anonymes prolongees

---

## ADR-006 : HMAC-SHA256 sur les payloads serialises en Redis

**Contexte :** Les modeles ML sont caches dans Redis via serialisation. Sans verification d'integrite, un attaquant ayant acces a Redis pourrait injecter des objets arbitraires.

**Decision :** Signer chaque payload avec HMAC-SHA256 (cle = `SECRET_KEY`) avant stockage. Verifier le HMAC avant deserialisation.

**Justification :**
- La deserialisation non verifiee est une vulnerabilite d'execution de code arbitraire
- HMAC est leger (32 bytes de overhead) et rapide
- Si le HMAC echoue, le cache est ignore (fail-safe : recalcul du modele)
- Utilise `hmac.compare_digest()` pour eviter les timing attacks

---

## ADR-007 : PSI pour la detection de data drift

**Contexte :** Sans monitoring, les modeles ML peuvent deriver silencieusement lorsque la distribution des donnees change.

**Decision :** Implementer le PSI (Population Stability Index) sur 4 features (returns, volatilite 10j, momentum 5j, log-prix) avec seuils 0.1/0.2.

**Justification :**
- PSI est le standard industrie pour detecter la derive (Basel II, credit scoring)
- Seuils 0.1 (warning) / 0.2 (drift) sont les valeurs de reference acceptees
- 4 features couvrent les aspects cles : niveau, direction, volatilite, momentum
- Execution quotidienne via Celery pour detection proactive

---

## ADR-008 : Cache hash SHA256 avec echantillonnage

**Contexte :** Le hash de cache Redis utilisait seulement 3 points (longueur, premier, dernier prix) — des series tres differentes pouvaient produire le meme hash.

**Decision :** Echantillonner 10+ points equidistants + extremes, hasher avec SHA256 (tronque a 16 chars).

**Justification :**
- 3 points ne distinguent pas `[100, 200, 300, 400, 500]` de `[100, 150, 250, 350, 500]`
- 10 points echantillonnes offrent un bon compromis collision/performance
- SHA256 est plus resistant aux collisions que MD5
- Tronque a 16 chars (64 bits) : probabilite de collision negligeable pour notre volume

---

## ADR-009 : Separation liveness/readiness probes

**Contexte :** Un seul endpoint `/health` combinait verification du process et des dependances.

**Decision :**
- `/health` : liveness (le process tourne-t-il ?)
- `/health/ready` : readiness (DB + Redis sont-ils accessibles ?)

**Justification :**
- Kubernetes/Railway distinguent les deux types de probes
- Un readiness check lent ne doit pas tuer le pod (liveness)
- `/health/ready` retourne HTTP 503 si une dependance est down
- Les logs filtrent `/health*` pour reduire le bruit

---

## ADR-010 : Deux librairies de graphiques — frontière d'usage et chunks séparés

**Contexte :** Le frontend embarque `@nivo/*` (bar, line, pie, radar) **et**
`lightweight-charts`. Le ticket d'audit ARC-10 demandait de « choisir par cas d'usage et
documenter, ou consolider ; retirer la lib non utilisée ».

**Mesure :** Nivo est importé dans **24 fichiers** ; Lightweight Charts dans **deux** —
`PortfolioAreaChart.tsx` et son thème. Aucune des deux n'est morte. `recharts`, annoncé
dans CLAUDE.md, n'a jamais été installé ni utilisé.

**Décision :** Garder les deux, avec une frontière explicite.

| Besoin | Librairie |
|---|---|
| Répartitions, comparaisons, radars, séries courtes non navigables | **Nivo** |
| Série temporelle financière navigable (pan, zoom, crosshair sur l'axe temps) | **Lightweight Charts** |

Un seul écran relève du second cas : la courbe de patrimoine du dashboard d'accueil.
Tout nouveau graphique passe par Nivo, sauf à avoir besoin de la navigation temporelle.

**Justification :** Nivo est déclaratif et thématisé, mais son `ResponsiveLine` ne navigue
pas dans le temps. Lightweight Charts fait exactement cela et rien d'autre. Porter la
courbe de patrimoine vers Nivo lui ferait perdre le crosshair et le zoom ; porter les 24
autres graphiques vers Lightweight Charts reviendrait à réécrire des camemberts et des
radars avec une librairie qui n'en propose pas.

**Le vrai coût n'était pas la cohabitation, mais le chunk.** `manualChunks` rangeait
`@nivo`, `d3-*` et `lightweight-charts` sous un même nom `charts` : **597 kB** (196 kB
gzip), le plus gros chunk du build, au-delà du seuil d'alerte de Vite. Toute page
affichant le moindre camembert téléchargeait donc aussi Lightweight Charts — et le
`lazy()` posé sur `PortfolioAreaChart` ne protégeait plus rien, puisque son code arrivait
avec celui de Nivo.

Les deux chunks sont désormais distincts :

| Chunk | Taille | Gzip |
|---|---|---|
| `charts-nivo` | 428 kB | 141 kB |
| `charts-timeseries` | 169 kB | 55 kB |

Les pages qui n'affichent pas la courbe de patrimoine — portefeuille, rapports,
simulations, crowdfunding — économisent **169 kB** (55 kB gzip). Le dashboard d'accueil,
qui utilise les deux, télécharge le même volume qu'avant en deux requêtes
parallélisables. L'avertissement Vite « chunks larger than 500 kB » disparaît.

**Garde-fou :** `src/components/charts/strategie-graphiques.test.ts` vérifie que
Lightweight Charts n'est importé que par les deux fichiers de sa portée, et que la
configuration maintient les deux chunks séparés. Sans ce second test, une refusion des
chunks annulerait le gain sans que rien ne le signale.
