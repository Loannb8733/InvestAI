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

---

## ADR-011 : Une seule instance web en production — pas de worker Celery, compteurs en mémoire

**Contexte :** `render.yaml` déclare trois services (API, worker Celery, beat). En
production (Render, offre gratuite) **seul `InvestAI-api` existe** — un uvicorn sans
`--workers`, variables d'environnement posées à la main sur le service (constaté le
2026-09-15). Les tâches planifiées passent par GitHub Actions
(`.github/workflows/scheduled-tasks.yml`) qui appelle `/api/v1/cron/*`. Redis est un
Upstash gratuit : **500 000 commandes par mois**, chaque commande facturée.

**Mesure (2026-09-15, quota épuisé) :** un worker Celery au repos coûtait 94 commandes
par minute (~4 millions par mois) ; un tableau de bord recalculé 107 ; une requête
authentifiée 4 avant tout travail utile (3 pour le limiteur, 1 pour la révocation) ;
chaque `.delay()` émis par le web empilait une tâche que rien ne consommait
(8 commandes, liste `celery` qui grossit sans fin).

**Décision :** le code sait sur quelle topologie il tourne, par deux réglages dont le
défaut décrit la production :

| Réglage | Défaut (prod) | docker-compose | Effet |
|---|---|---|---|
| `CELERY_WORKER_AVAILABLE` | `False` | `true` | Sans worker, `planifier_cache_historique()` confie le pré-chargement à la boucle asyncio du web (une fois par symbole et par heure) au lieu de mettre en file |
| `RATE_LIMIT_SHARED_STORAGE` | `False` | (défaut) | Compteurs du limiteur en mémoire du processus ; à passer à `True` dès qu'une seconde instance existe, sinon chaque instance compte de son côté |

Règles qui en découlent : un client Redis par processus (jamais par appel), lectures
groupées (`MGET`) plutôt qu'une commande par symbole, pas d'annonce de version
(`lib_name=None`), délai réseau sur tout client (`redis_client_kwargs()`), et
PostgreSQL écrit **avant** Redis pour l'historique des cours — la base est la copie
durable, le cache un accélérateur.

**Conséquences :** recalcul du tableau de bord ≈ 25 commandes, requête authentifiée 1,
cache servi 2. Le worker local reste sobre (`polling_interval`, sans heartbeat).
Le jour où un worker existe en production, poser `CELERY_WORKER_AVAILABLE=true` sur
le service web suffit ; le jour où une seconde instance web existe, poser
`RATE_LIMIT_SHARED_STORAGE=true` sur toutes. Détail des mesures : `docs/audit/BACKLOG.md`,
NEW-77 à NEW-87.


## ADR-012 : Architecture par domaine, transaction par requête, démarrage découpé

**Contexte :** la logique métier, les requêtes SQL et les commits vivaient dans les
endpoints (84 commits dans `api/`), `main.py` faisait 1 130 lignes, et les fichiers de
plus de 1 000 lignes se comptaient par dizaines. La refonte migre le backend domaine
par domaine ; `journal` (les notes) est le domaine pilote.

**Décision — structure d'un domaine** (`app/domains/<domaine>/`) :

| Fichier | Rôle | Interdit |
|---|---|---|
| `router.py` | HTTP : valide, appelle le service, rend un schéma | requête SQL, commit, règle métier |
| `schemas.py` | Pydantic d'entrée et de sortie | — |
| `models.py` | SQLAlchemy typé (`Mapped[...]`) | — |
| `repository.py` | toutes les requêtes du domaine | `commit` (au plus `flush`) |
| `service.py` | cas d'usage, lève des `DomainError` | `commit`, `HTTPException` |
| modules purs (ex. `scorecard.py`) | calcul sans I/O | accès base |

Un domaine lit les données d'un autre par ses **tables** (`Model.__table__.c`) et les
rend sous des types qui lui appartiennent (ex. `AssetRef`), jamais en manipulant les
classes ORM de l'autre domaine.

**Décision — transaction :** pas de classe `UnitOfWork`. La dépendance
`core.db.session.get_session` ouvre la session, commit si la requête aboutit, rollback
sinon (`HTTPException` et `DomainError` comprises). Une classe enveloppant la session
n'apporterait rien ; une classe exposant les repositories de tous les domaines
deviendrait un fourre-tout. `core.db.metadata.metadata` charge tous les modèles :
`create_all` et Alembic l'utilisent.

**Décision — erreurs :** les services lèvent `core.errors.DomainError` (et ses
sous-classes, ajoutées quand un domaine en a besoin). `core.error_handlers` les rend en
`{"detail": ...}`, la forme d'une `HTTPException`, et traite aussi les exceptions non
gérées (500 journalisée, détail masqué en production) et le dépassement de quota.

**Décision — démarrage :** `main.py` ne fait qu'assembler l'application
(`create_app`). `core/http/` porte les middlewares (enregistrés dans le même ordre
qu'avant : journalisation, GZip, CORS, en-têtes de sécurité, invalidation du cache du
dashboard), `core/health.py` les sondes, `core/startup/` le verrou de démarrage,
Alembic puis `create_all`, puis trois **auto-réparations idempotentes** :

| Auto-réparation | Ce qu'elle répare | Chemins d'écriture qui produisent encore ces données (2026-10-19) |
|---|---|---|
| `multiplatform` | transaction dont la plateforme diffère de celle de son actif | `PATCH /transactions/{id}` sur `exchange` (aucune nouvelle répartition) |
| `transfer_mirrors` | `TRANSFER_OUT` sans miroir valide, hors notes d'ajustement interne (incident Tangem du 2026-06-07 : 5 positions fantômes) | sortie manuelle ou CSV sans destination ; échec du miroir pendant la synchro ; `PATCH` du type |
| `rehash` | `internal_hash` absent ou périmé, collisions mises à `NULL` en libérant avant d'occuper (ordre des UPDATE, 2026-09-10) | import d'historique (`compute_hash` jamais appelé) ; `PATCH` des montants |

Elles restent au démarrage tant que ces chemins existent : en faire des migrations à
usage unique changerait le comportement. Elles disparaîtront quand les domaines
`transactions` et `exchanges` corrigeront ces écritures à la source.

**Conséquences connues, non traitées ici :**
- 13 index créés par des migrations ne sont déclarés dans aucun modèle : une base neuve
  (`create_all` puis marquage à la tête) ne les a pas. Chaque domaine déclare ses index
  dans ses modèles lors de sa migration.
- La première migration (`001`) suppose la table `users` : l'historique Alembic ne sait
  pas créer une base vierge. Le chemin d'une base neuve reste `create_all` + marquage.
- `c4e8f1a2b3d5` fait converger `transactions.quantity/price/fee` vers les précisions du
  modèle (élargit seulement, jamais de réduction) et ajoute `fee_currency`, qu'aucune
  migration ne créait ; elle remplace `scripts/migrate_fee_currency.py`, qui ramenait
  `fee` en `NUMERIC(18, 8)` et aurait tronqué les frais.

## ADR-013 : Historique de prix — la base seule, jamais de réseau pendant une requête

**Statut :** accepté (2026-10-19)

**Contexte :** trois caches d'historique coexistaient (`hist:<sym>:<type>:<jours>` en
Redis asynchrone, `hist:<SYM>_<jours>` et sa copie `:fallback` en Redis synchrone,
`asset_price_history` en base), lus dans des ordres différents selon l'appelant. Une
partie des pages web appelait CoinGecko ou Yahoo pendant la requête (benchmarks,
analytics, prédictions, variations de période), une autre l'interdisait : la cause des
65 s de `/predictions/market-cycle` (NEW-13). Les cotations Yahoo des actions étaient
enregistrées dans leur devise de cotation sous `price_eur`, et l'immobilier physique
recevait un historique tiré au hasard, utilisé ensuite dans la VaR et les corrélations.

**Décision :** `domains/market_data/history` :
- `asset_price_history` est l'unique source d'historique (plus de cache Redis) ; une
  colonne `volume` y conserve les volumes utilisés par les prédictions ;
- `reader.local_history` / `local_series` lisent la base, sans réseau, pour tout le code
  web ; un symbole absent rend une série vide et peut être programmé avec
  `tasks.schedule_refresh` ;
- seules les tâches (`refresh_history` toutes les 30 min, `backfill_history` chaque jour,
  `refresh_one`, préchargement au démarrage) interrogent CoinGecko (un appel à la fois,
  `Retry-After` respecté), puis Yahoo en repli (paire `<SYM>-EUR` pour une crypto) ;
- toute cotation Yahoo est convertie en euros au taux BCE du jour ; un jour sans taux est
  écarté ;
- les références de marché (BTC, SPY, IWDA.AS, ^GSPC, ^IXIC, PAXG) sont rafraîchies avec
  les actifs détenus ;
- un actif sans cotation (immobilier, crowdfunding) n'a pas d'historique.

**Conséquences :** une page dont l'historique n'a pas encore été chargé affiche une série
incomplète au lieu d'attendre une API tierce. La migration `d5f9a3b4c6e7` ajoute
`volume` et supprime les lignes d'actions et d'ETF, rechargées converties au passage
suivant de la tâche.
