# InvestAI — Backlog priorisé d'après l'audit du 2026-06-03

> Source : 4 rapports d'audit (`01-calculs-financiers.md`, `02-architecture-code.md`, `03-fonctionnalites-ux.md`, `04-securite-donnees.md`).
> Couvre **45 findings**. Chaque ticket renvoie à son/ses ID(s) d'origine.

---

## ⚠️ Mises à jour des 2026-08-31 et 2026-09-01 — lire avant de reprendre ce backlog

Une session de travail sur les données **réelles de production** a invalidé plusieurs
hypothèses de l'audit. Ce qui suit prime sur le reste du document.

### Ce qui était faux dans l'audit

| Affirmation de l'audit | Réalité mesurée |
|---|---|
| FIN-01 « non entamé », P0 🔴 | **Déjà implémenté à ~80 %** avant la session : `pair_utils`, `_resolve_trade_fx`, `_heal_transaction_fx`, `fx_history_service`, script de backfill et 5 fichiers de tests existaient. |
| « coût de base faux de ~8-9 % pour la majorité des traders crypto » | **0 ligne concernée en production.** Les 164 achats/ventes du compte sont réellement en EUR. Le correctif reste juste, mais ne justifiait pas la priorité P0 *pour cet usage*. |
| FIN-01 localisé dans `tasks/sync_exchanges.py` | Périmètre incomplet : `services/csv_parsers.py:639` force aussi `currency="EUR"` sans lire de colonne devise. |
| Les 11 violations de l'invariant A | Ni un bug de calcul ni un historique « incomplet » : **5 étaient des écritures fantômes** créées par le mirroring (voir NEW-02). |

**Leçon de méthode** : chaque ticket de ce backlog a été écrit en lisant du code, pas en
mesurant des données. Avant d'investir sur FIN-02 ou FIN-04, **mesurer d'abord l'exposition
réelle** — le diagnostic prend dix minutes et peut annuler des jours de travail.

Trois erreurs de la session du 2026-08-31 valent d'être consignées, elles se ressemblent :

1. **Réparer un symptôme sans chercher sa cause.** L'écart entre solde et historique a été
   « comblé » par 7 écritures de réconciliation (NEW-06). La cause réelle était en amont
   (NEW-09) ; le correctif a empilé une troisième couche sur un double comptage et coûté
   **214 € de plus-value affichée**. Toujours remonter à la cause avant d'écrire en base.
2. **Corriger un indicateur sans regarder le chiffre affiché.** L'invariant est passé au
   vert pendant que le P&L se dégradait. Un contrôle technique n'est pas une fin : mesurer
   AVANT/APRÈS sur ce que l'utilisateur voit réellement.
3. **Conclure sans mesurer.** Un correctif a été déclaré défaillant (clé API révoquée,
   angle mort de conception) alors que la sync était simplement asynchrone et n'avait pas
   encore abouti. Attendre et mesurer, plutôt que raisonner.

4. **Un garde-fou ne doit pas dépendre de ce qu'il protège.** Le refus des scripts
   destructeurs était prononcé après `from app.core.database import …`. Hors conteneur,
   l'import échouait d'abord : le script sortait en erreur sans jamais dire pourquoi, et
   la CI restait rouge (NEW-12). Un contrôle de sécurité doit s'exécuter **avant** toute
   dépendance faillible — ici, la stdlib suffit.

Corollaire sur les tests : deux tests écrits ce jour-là passaient au vert **sans rien
vérifier** — l'un cherchait `executed_at` et trouvait le mot dans un commentaire voisin.
Tout test de non-régression doit être validé par un canari : casser volontairement le code
et vérifier que le test échoue. C'est exactement le reproche que ce backlog fait aux tests
parity/XIRR (FIN-TEST).

### Livré le 2026-08-31

| Ticket | État | Détail |
|---|---|---|
| **UX-01** | ✅ | La redirection `/strategies` existait déjà ; l'apport est le garde-fou croisant chaque entrée de menu avec les `<Route>` d'`App.tsx`. Vérifié à l'écran : 12 entrées, 0 404. |
| **FIN-01** | ✅ | Backfill élargi aux trades order-book et aux « Instant Buy » (oubliés). Sur la base de dev : 0 → 15 lignes corrigées. En prod : 0 ligne concernée. |
| **FIN-TEST** | ✅ | Le reproche (« XIRR juste borné [-95,1000], parité tolérée à 1 % ») décrit un état périmé. Les tests affirment des valeurs exactes : XIRR 10 000→11 000 sur 1 an = **10 %** (±0,002), doublement = 100 %, perte = −20 %, NPV nul à la solution ; parité = **863,90 €** au centime ; les transferts ne modifient pas le XIRR ; dividendes comptés. **65 tests numériques déterministes ajoutés** dans la session par-dessus (FX, Earn, mirroring, cookie, matérialité, garde-fous). |

### Findings découverts en session (absents de l'audit)

| ID | Sév. | Problème → Correctif | État |
|---|---|---|---|
| **NEW-01** | 🔴 | `start.sh` ne démarrait rien : `"${@:-up -d}"` s'expanse en UN mot, rejeté par `docker compose`. | ✅ corrigé |
| **NEW-02** | 🔴 | Le mirroring traitait tout `TRANSFER_OUT` comme un retrait vers le cold wallet. Une opération de **nettoyage** (`Phantom holding zeroed`) a ainsi créé 5 entrées fantômes sur Tangem (109 529 PEPE, 25,21 USDT, 2,52 USDG, 0,0086 DOGE) pour des actifs jamais détenus là-bas. 57 ajustements internes restaient sélectionnables. → Exclusion des libellés d'ajustement, en paramètre lié. | ✅ corrigé + données nettoyées |
| **NEW-03** | 🔴 | Le mirroring **recalculait** `asset.quantity` depuis l'historique, en le supposant exhaustif — impossible pour un cold wallet. → Incrément du montant miroité. Le rattrapage « Always recalculate ALL Tangem assets » a été supprimé : il aurait réintroduit les fantômes à chaque appel. | ✅ corrigé |
| **NEW-04** | 🟠 | Une position Earn refermée laissait son marqueur `STAKING` figé indéfiniment : **404,14 € affichés** dans le patrimoine pour une position inexistante. Le type `UNSTAKING` existait sans être jamais généré. | ✅ corrigé **et validé en prod** : une sync Binance a écrit l'`UNSTAKING` automatiquement (libellé « Auto: sortie d'Earn/Staking »), les 404 € ont disparu |
| **NEW-05** | 🟠 | La CI échouait sur **tous** les runs depuis ≥ 11/07 : `COOKIE_SECURE` n'était abaissé qu'en `development`, or la CI tourne en `testing` — le cookie n'était pas renvoyé, la révocation de jeton intestable. | ✅ corrigé, CI verte |
| **NEW-06** | 🟠 | Historique **négatif** sur 3 actifs (USDC Binance −26,55). Diagnostic initial FAUX : on a cru à des entrées manquantes hors fenêtre de sync et écrit 7 `TRANSFER_IN` de réconciliation. **Elles ont dégradé le P&L affiché de 214 €** (+252 € → +38 €) car le FIFO comptait déjà ces actifs. La vraie cause était NEW-09. | ↩️ **annulé** — les 7 lignes ont été supprimées ; `scripts/reconcile_missing_entries.py` **ne doit pas être relancé** en l'état |
| **NEW-07** | 🟡 | **Divergences de schéma dev/prod** : `prediction_logs.price_at_creation` absent en dev ; la FK `related_transaction_id` a `ON DELETE SET NULL` en dev mais pas en prod. Ce qui est validé en dev ne garantit donc pas le comportement en prod. | ✅ corrigé — migration idempotente `s0n1o2p3q4r5` (`ADD COLUMN IF NOT EXISTS`, FK recréée seulement si `confdeltype` diffère) |
| **NEW-08** | 🟡 | `recalc_avg_price.py` et `recalculate_quantities.py` recalculent `avg_buy_price` **sans lire `conversion_rate`** : les lancer défait FIN-01. | ✅ neutralisés — `_danger_guard.py` exige `--i-know-what-im-doing`, refus motivé sinon |
| **NEW-09** | 🔴 | **La sync fabriquait des ajustements annulant ses propres trades.** La réconciliation de solde comparait notre quantité à celle de l'exchange sans tenir compte des trades qu'elle venait d'écrire : le 2026-08-04 sur Kraken, 4 achats (BTC 0,00332921 · ETH 0,02996601 · PAXG 0,00689502 · SOL 0,37863) ont chacun été suivis d'un « Ajustement balance » de quantité EXACTEMENT égale et de sens opposé. L'historique perdait les achats, le solde les gardait — et l'écart se lisait ensuite comme un « historique incomplet », d'où NEW-06. → `contradicts_recent_trade()`. | ✅ corrigé + 4 lignes supprimées |
| **NEW-10** | 🔴 | **199 transactions sans `executed_at`** (152 TRANSFER_IN, 47 TRANSFER_OUT). Le FIFO trie par `(executed_at ?? epoch, …)` : sans date, la ligne est rejouée en 1970, AVANT tout achat, sur un stock vide — elle ne retire donc aucun coût, alors que la somme signée la décompte. **C'est la racine de la divergence CUMP/FIFO du ticket FIN-03.** Les 3 sites concernés (ajustement de balance, import initial, mise à zéro) datent désormais leurs écritures. | ✅ corrigé |
| **NEW-11** | 🟡 | L'invariant `check_holdings_qty` sortait en échec pour tout écart, même d'un millionième d'euro : le watchdog était rouge en permanence, donc plus lu. → Seuil de matérialité (position soldée < 1 € · écart < 0,01 €), écarts listés en WARN avec leur raison, code de sortie fondé sur les seules violations matérielles. | ✅ corrigé |
| **NEW-12** | 🟠 | **Le garde-fou des scripts dangereux ne protégeait pas dans un environnement dégradé.** `require_consent()` était appelé en fin de fichier, donc après `from app.core.database import …`. Or ces scripts font `sys.path.insert(0, "/app")` — le chemin du conteneur. Hors conteneur, l'import échouait sur `ModuleNotFoundError` avant que le garde soit atteint : sortie en code 1, mais sans message et pour la mauvaise raison. **La CI était rouge depuis 6 exécutions** pour cette raison. → Refus remonté au-dessus de tout import applicatif (stdlib seule) + second `sys.path.insert` portable. | ✅ corrigé, CI verte |

**Invariant A (`check_holdings_qty`)** : 11 violations → **0 violation matérielle** (4 avertissements sur des poussières), code retour 0. Vérifié en production.

**P&L du portefeuille Crypto** : +252 € après nettoyage, contre +38 € au plus bas de la session. Contrôle indépendant : le PRU BTC/Kraken calculé tombe sur celui affiché par Kraken (55 544 €).

### Livré le 2026-09-01

| Ticket | État | Détail |
|---|---|---|
| **ARC-01** | ✅ | 9 fichiers, 8 helpers `run_async` dupliqués → **1 seul** (`tasks/async_runner.py`) ; l'engine passe en `NullPool` quand il tourne dans un worker Celery (détection par `sys.argv` ou `DB_NULLPOOL`). |
| **SEC-01** | ✅ | Le webhook Telegram n'est plus ouvert en l'absence de secret. |
| **SEC-02** | ✅ | `GET /import-status/{task_id}` ne renvoie plus `{type(e).__name__}: {e}` au client. |
| **UX-04** | 🟢 **14 / 17** | Composant `QueryErrorState` créé (détail technique visible sous `import.meta.env.DEV` seulement, bouton uniquement si `onRetry`). Sur les 17 pages qui émettent une requête, 14 gèrent l'échec, contre 6 au départ. **Restent 3** : `ExchangesPage`, `ReportsPage`, `SettingsPage` — elles traitent l'erreur de *mutation* (toast) mais pas l'échec de chargement. |
| **ARC-05** | ✅ | `prediction_service.py` **2 416 → 1 655 lignes** ; 761 lignes extraites dans `prediction_alpha.py` (`PredictionAlphaMixin`). |
| **ARC-07** | 🟢 partiel | `ExchangesPage.tsx` **1 368 → 1 286 lignes** ; `ExchangeLogo` et les types extraits. Le découpage complet est **volontairement différé** : sans tests de rendu sur cette page, un découpage large casserait en silence. |
| **FX quotidien** | ✅ | Tâche Celery `refresh_fx_rates` (USD/GBP/CHF → EUR), `crontab(hour=16, minute=5)` — les taux ne dépendaient plus d'une synchronisation pour être rafraîchis. |
| **NEW-07** | ✅ | Migration d'alignement dev/prod, idempotente. |
| **NEW-08** | ✅ | Les deux scripts destructeurs exigent un consentement explicite. |
| **NEW-12** | ✅ | CI **verte** : 5 jobs sur 5, après 6 exécutions rouges consécutives. **1 208 tests** au vert. |

### Bilan de l'EPIC A : les 5 tickets étaient déjà traités

| Ticket | Verdict après mesure |
|---|---|
| FIN-01 | implémenté à ~80 % ; complété. **0 ligne concernée en prod** |
| FIN-02 | les 3 griefs traités dans `analytics_math.py`. **0 transaction non-EUR, 0 dividende**. XIRR = 11,51 % |
| FIN-03 | le FIFO était correct ; la cause était en amont (NEW-09/NEW-10) |
| FIN-04 | service unique, table ECB persistée, `forex_stale` propagé, 0 `except: pass`. Restait le rafraîchissement (corrigé) et la conversion des frais crypto (corrigée) |
| FIN-TEST | valeurs exactes déjà vérifiées ; reproche périmé |

**Aucun des cinq n'a été trouvé dans l'état décrit par l'audit.** Les vrais défauts —
sync fabriquant des ajustements contradictoires, transactions sans date, positions
fantômes, marqueur Earn figé, CI rouge depuis juillet — n'y figuraient pas.

### Décision d'architecture (2026-09-01) : le SOLDE fait foi

Le FIFO et la somme signée des transactions divergent structurellement sur les
transferts. La question « quelle source fait foi ? » est tranchée :

**`asset.quantity` fait foi.** L'historique est un journal, incomplet par nature :
un cold wallet n'a pas d'API pour ses sorties, et la synchronisation ne remonte
qu'une fenêtre limitée. La session l'a vérifié à chaque fois — les soldes étaient
justes, l'historique non.

Conséquences pratiques :
- l'invariant `check_holdings_qty` est un **indicateur**, pas une vérité : un écart
  signale un journal incomplet, pas un solde faux ;
- **on ne réécrit jamais `asset.quantity` depuis l'historique** (cf. NEW-03) ;
- on ne « comble » pas l'historique pour faire taire l'invariant : c'est ce qui a
  coûté 214 € de plus-value affichée (NEW-06).

### Mesure des EPICs restants (2026-09-01)

Après cinq tickets FIN trouvés déjà faits, les EPICs suivants ont été mesurés plutôt
que lus. **Contrairement à l'EPIC A, ceux-ci sont réels.**

| Ticket | Annoncé par l'audit | Mesuré | Verdict |
|---|---|---|---|
| **ARC-01** | 7 fichiers `new_event_loop` | **9 fichiers**, 8 helpers `run_async` dupliqués | ✅ réel, **aggravé** (dont un ajouté le 2026-09-01 par `fx_rates.py`, en suivant la convention en place) |
| **ARC-02** | 0 `relationship()` → « N+1 » | 0 `relationship()`, mais **le N+1 n'existe pas** : 50 actifs → 8 requêtes, 6 actifs → 1 ; 3 requêtes pour 2 portefeuilles + 56 actifs + 840 transactions | ❌ **infondé** — voir ci-dessous |
| **ARC-03** | `transactions.py` 70 req · `dashboard.py` 37 · `api_keys.py` 59 | 70 · 22 · 56, pour 1 671 / 1 383 / 1 876 lignes | ✅ réel (dashboard amélioré depuis) |
| **UX-03** | actions/ETF/immobilier « absents » | types présents au modèle, `get_stock_price` existe, mais **0 actif** de ces types et aucune page dédiée | ⚠️ réel mais **à reformuler** : ce n'est pas l'absence de support, c'est l'absence de parcours |

#### ARC-02 : pourquoi le ticket se contredit

Le N+1 est un symptôme du **lazy loading** des relations ORM : on charge N objets,
puis on touche un attribut de relation sur chacun, ce qui déclenche N requêtes
supplémentaires. Il faut donc des `relationship()` pour en souffrir.

Or il n'y en a aucun, et `Asset` n'expose aucun attribut de relation : le lazy
loading est **structurellement impossible**. Les « jointures FK manuelles » que le
ticket reproche sont exactement ce qui l'empêche.

Mesuré : le nombre de requêtes est **constant**, indépendant du volume.

| Portefeuille | Actifs | Requêtes |
|---|---:|---:|
| Crypto | 50 | 8 |
| Crowdfunding | 6 | 1 |

Appliquer le correctif proposé (`relationship(..., lazy="selectin")` sur les cinq
modèles centraux) **introduirait** le risque : chaque chargement d'actif tirerait ses
transactions, y compris là où le code n'en a pas besoin. On remplacerait un accès
groupé explicite par un chargement implicite plus coûteux.

Ce qui reste vrai dans le ticket : le code est verbeux, les jointures sont écrites à
la main. C'est un sujet de confort, pas de performance — et il ne justifie pas la
priorité 🟠 ni le risque du correctif proposé.

#### EPICs D, E, F et H — mesurés le 2026-09-01

**EPIC E (sécurité)** — les deux P1 étaient réels et sont traités :

| Ticket | Mesuré | Verdict |
|---|---|---|
| SEC-01 | vérif conditionnée à l'existence du secret : sans secret, webhook ouvert | ✅ **réel**, corrigé |
| SEC-02 | `{type(e).__name__}: {e}` renvoyé par `GET /import-status/{task_id}` | ✅ **réel**, corrigé |
| SEC-03 | `/register` renvoie « Un compte avec cet email existe déjà » | ✅ **réel**, impact faible |
| SEC-04 | 2 sous-points sur 3 déjà corrigés ; l'endpoint admin est pire que décrit | ⚠️ **1/3 réel** |
| SEC-05 | fail-open déjà décidé et loggué ; IDOR non exploitable ; docstring trompeuse | 🟢 **partiel** |
| SEC-06 | `python-jose` **3.4.0** — les CVE citées visent ≤ 3.3.0 | ❌ **périmé** |

##### SEC-03 à SEC-06 — le détail (mesuré 2026-09-01)

**SEC-03** est réel. L'argument décisif n'est pas théorique mais l'incohérence interne :
les deux routes voisines portent des docstrings explicites — « Always returns success to
avoid email enumeration » (forgot-password), « Always return success to prevent email
enumeration » (resend). Seul `register` a été oublié. Exposition réelle : route publique,
limitée à 3/min, mais **1 seul utilisateur en base** — l'oracle ne révèle que l'adresse du
propriétaire. Correctif XS, à faire pour la cohérence plus que pour le risque.

**SEC-04** — les deux durcissements que le ticket réclame sont déjà en place :

| Sous-point | Verdict |
|---|---|
| `X-Forwarded-For` spoofable | ❌ **déjà corrigé** — `rate_limit.py:20-27` lit la chaîne **depuis la droite** via `TRUSTED_PROXY_HOPS=1`, avec le commentaire qui explique pourquoi le leftmost est falsifiable |
| Redis TLS `CERT_NONE` | ❌ **déjà corrigé** — `CERT_REQUIRED` forcé (`config.py:160`), `ssl_cert_reqs="required"` (`redis_client.py:40`) |
| Endpoint admin verbeux | ✅ **réel, et pire que décrit** |

`admin_fix_mirrors` (`main.py:940`) fait **232 lignes** et dépasse de loin le « dump debug » :
il exécute un `ALTER TABLE` **en runtime depuis une requête HTTP**, renvoie au client la
liste de toutes les transactions de transfert (id, symbole, exchange, type) via son tableau
`log`, et **c'est le code qui a produit les 5 entrées fantômes Tangem** (NEW-02/NEW-03).
Atténuations : `get_current_admin_user` + 2/min. Le vrai sujet n'est pas la fuite
d'information, c'est qu'un endpoint HTTP migre le schéma et réécrive des soldes.

→ **Recommandation : supprimer l'endpoint**, ne pas le réduire. Son rôle est celui d'une
migration Alembic, il n'a plus de raison d'être appelé, et il reste le chemin par lequel
les fantômes sont entrés.

**SEC-05** — trois sous-points sur quatre ne tiennent plus, ou pas comme écrit :

- *Fingerprint* : réel, mais c'est un problème de **documentation**, pas de code. La
  docstring affirme « preventing stolen tokens from being used in a different browser »
  alors qu'un User-Agent se recopie en une ligne. Le ticket demandait précisément d'en
  documenter la limite — non fait.
- *Ownership sur `import-status`* : réel mais **non exploitable**. `_import_tasks` ne
  stocke aucun `user_id`, mais le `task_id` est un `uuid4().hex` (non énumérable) et le
  message d'erreur est générique depuis SEC-02.
- *Fail-open* : ❌ **plus « silencieux »**. La décision est prise, commentée (« the token
  still expires within minutes ») et logguée en WARNING aux deux endroits (`deps.py:115`,
  `auth.py:517`). Ne manque que l'alerte Redis.

**SEC-06** est périmé. `python-jose` est épinglé en **3.4.0** — la version qui corrige les
deux CVE invoquées (elles visent ≤ 3.3.0) — et `requirements.txt:14` le documente déjà en
commentaire. À l'usage, `jwt.decode(..., algorithms=[settings.ALGORITHM])` est imposé aux
deux points de vérification, ce qui neutralise la confusion d'algorithme indépendamment de
la version. Reste `bcrypt==4.0.1`, ancien. **Point utile découvert au passage** : `passlib`
n'est pas installé, bcrypt est appelé directement — l'obstacle habituel à la montée de
version (incompatibilité passlib / bcrypt ≥ 4.1) n'existe pas ici. Rounds à 12, conforme.

**EPIC F (god-files)** — trois confirmés, un largement fait :

| Ticket | Mesuré | Verdict |
|---|---|---|
| ARC-05 | `prediction_service.py` = **2 416 lignes** | ✅ réel |
| ARC-07 | `ExchangesPage.tsx` = **1 368 lignes** | ✅ réel |
| ARC-11 | aucun util de formatage ; **13 fichiers** formatent les montants à la main | ✅ réel |
| ARC-09 | `lib/queryKeys.ts` existe (184 l.) et est importé par **43 fichiers** | ⚠️ **quasi fait** — restent 17 clés en ligne |

**EPIC H (polish)** — deux tickets sont périmés :

| Ticket | Mesuré | Verdict |
|---|---|---|
| FIN-05 | la docstring dit déjà « negative = cash outflow, positive = cash inflow » | ❌ **déjà correct** |
| ARC-12 | `fetchUser` est utilisé (`VerifyEmailPage.tsx`) — ce n'est pas un alias mort | ❌ **infondé** |
| UX-09 | le `<h1>` du Login porte `font-semibold`, pas `font-serif` | ✅ réel (polish) |

**EPIC D (UX)** — le plus solide des quatre :

| Ticket | Mesuré | Verdict |
|---|---|---|
| UX-04 | **6 pages sur 32** gèrent un état d'erreur | ✅ réel, le plus large |
| UX-08 | 48 fichiers à spinner contre 19 à skeleton | ✅ réel |
| UX-05 | « Objectifs » → `/strategy` et « Stratégies » → `/strategies` cohabitent toujours | ✅ réel |

**Ce que la mesure de bout en bout donne** : sur **24 tickets vérifiés**, **11 sont
infondés, périmés ou déjà faits** (5 FIN de l'EPIC A, ARC-02, FIN-05, ARC-12, SEC-06, et
2 des 3 sous-points de SEC-04) et **13 sont réels** — dont plusieurs à une sévérité bien
inférieure à celle annoncée.

L'audit se trompe systématiquement là où le code a bougé depuis juin, et voit juste sur ce
qui n'a jamais été touché — god-files, états d'erreur. **La lecture « la sécurité est le
domaine où l'audit voit juste » ne tient plus** après mesure de l'EPIC E : sur 6 tickets
SEC, 2 étaient réels (SEC-01/02, corrigés), 1 l'est faiblement (SEC-03), 1 à un tiers
(SEC-04), 1 partiellement (SEC-05) et 1 est périmé (SEC-06).

Deux constats se répètent d'un EPIC à l'autre :
- **les chiffres de l'audit sont faux quand ils sont vérifiables** — 3 733 vs 2 416 lignes,
  2 185 vs 1 368, 43 vs 13 fichiers, et un dénominateur de 36 pages pour UX-04 quand
  **17** seulement émettent une requête ;
- **la sévérité annoncée ne survit pas à la mesure d'exposition** — un oracle
  d'énumération sur une base d'un seul utilisateur, un IDOR protégé par un `uuid4`, des
  CVE corrigées par la version déjà épinglée.

**Priorité recommandée au 2026-09-01** — UX-04, ARC-05 et SEC-01/02 étant livrés :

**Le backlog est désormais intégralement mesuré** — plus aucun ticket n'est pris sur
parole.

1. **Supprimer `admin_fix_mirrors`** (SEC-04) — le seul point de ce lot qui mérite du
   travail, et pas pour la raison écrite au ticket : un endpoint HTTP qui exécute un
   `ALTER TABLE` et réécrit des soldes. C'est par là que les fantômes Tangem sont entrés.
   **SEC-03** en complément (~10 min).
2. **UX-05** (taxonomie Objectifs/Stratégies) et **ARC-11** (formatage monétaire dans
   13 fichiers) — réels, mesurés, sans dépendance.
3. **VERIF-01** — le 8,5/10 de design reste une hypothèse non vérifiée.
4. **ARC-07 (suite)** et **ARC-03** (`transactions.py`, 1 671 lignes) — à faire précéder
   de tests de rendu / de service, faute de quoi le refactor casse en silence.
5. **UX-04 (fin)** — les 3 pages restantes, puis l'alerte Redis (SEC-05) et la docstring
   du fingerprint. Polish.

### Ce que FIN-03 était réellement

Le ticket décrivait « TRANSFER_IN non apparié → couche à coût zéro ; règle divergente CUMP vs FIFO ». Le moteur FIFO s'est révélé **correct** : ses couches transitent bien d'un wallet à l'autre. La divergence venait d'en amont — des écritures d'ajustement sans date (NEW-10) et des ajustements annulant des trades (NEW-09). Corriger le FIFO aurait été corriger le mauvais composant.

---

## Note préalable sur l'objectif « 10/10 partout »

Je ne vais pas valider ce cadrage tel quel — il est en partie contre-productif :

- **Sécurité** : un « 10/10 » figé n'existe pas. C'est un processus (veille CVE, rotation, monitoring), pas un état atteint puis quitté. La cible utile = **0 finding 🔴/🟠 ouvert + contrôles continus en place**, pas un chiffre.
- **UX** : la qualité se mesure sur des utilisateurs réels (taux de complétion, support), pas sur une checklist. Un 10/10 auto-attribué n'a aucune valeur.
- **Design (8,5/10)** : ce score est **NON VÉRIFIÉ**. Il vient d'un agent qui a lu le CSS (tokens OKLCH, serif, glass/glow), pas qui a regardé l'app rendue. Voir des tokens premium ne prouve pas qu'un écran *paraît* premium — c'est exactement le piège que ta note mémoire dénonce. Tant que l'app n'est pas rendue et regardée écran par écran (ticket **VERIF-01**), ce 8,5 reste une hypothèse.

**Ce que vise réellement ce backlog** : éliminer tous les findings 🔴/🟠 (exactitude + sécurité + navigation), réduire la dette structurelle sous un seuil maintenable, et instaurer des garde-fous (tests numériques de référence, états d'erreur, monitoring) qui *maintiennent* la qualité dans le temps. C'est ça, « bien » — pas un 10 cosmétique.

---

## Légendes

**Priorité** — P0 = exactitude des montants ou casse visible en prod (à faire d'abord) · P1 = sévérité élevée (exploitable ou structurel) · P2 = moyen · P3 = polish / faible.
**Effort** — XS < 1 h · S ≈ 0,5 j · M ≈ 1–2 j · L ≈ 3–5 j · XL > 1 sem.
**Sév.** — 🔴 Critique · 🟠 Élevé · 🟡 Moyen · 🔵 Faible.

---

## Séquencement recommandé (vagues)

| Vague | Contenu | Pourquoi |
|-------|---------|----------|
| ~~**1 — Exactitude**~~ ✅ | ~~EPIC A (FIN-01→04) + FIN-TEST + UX-01~~ | ✅ **Close le 2026-09-01.** Les 5 tickets FIN mesurés étaient déjà traités ; FIN-02 mesuré (0 transaction non-EUR, 0 dividende, XIRR 11,51 %), FIN-04 complété (rafraîchissement FX quotidien + conversion des frais payés en crypto). L'estimation « ~8-9 % pour la majorité des traders » ne s'est PAS vérifiée : **0 ligne concernée en prod**. |
| **2 — Robustesse & vérité produit** | ✅ ARC-01 · ✅ EPIC E P1 (SEC-01/02) · **restent** ARC-03, ARC-04, EPIC B | ARC-02 écarté après mesure (le N+1 n'existe pas). EPIC B (onboarding, promesses d'actifs absents, titrage) n'a pas encore été mesuré. |
| **3 — Cohérence UX & sécurité moyenne** | 🟢 UX-04 (14/17) · **reste utile** : supprimer `admin_fix_mirrors` (SEC-04), SEC-03, UX-05→08, EPIC G | SEC-03→06 mesurés le 2026-09-01 : SEC-06 périmé, SEC-04 réel à un tiers, SEC-05 partiel. Le seul point sérieux est l'endpoint admin. |
| **4 — Dette & polish** | EPIC F (god-files) + EPIC H (P3) | Refactors à dérouler en continu, sans bloquer la valeur. |

> **VERIF-01** (rendu design) est à faire dès la vague 1 ou 2 : sans elle, on ne sait pas si le chantier design existe.

---

## EPIC A — Exactitude financière (P0)

> Racine commune des deux premiers tickets : `Transaction.currency` est faux ou ignoré. À traiter ensemble pour garantir la parité dashboard ↔ XIRR ↔ rapports.

| Ticket | Sév. | Source | Fichiers | Problème → Correctif | Critères d'acceptation | Effort |
|--------|------|--------|----------|----------------------|------------------------|--------|
| ✅ **FIN-01** Devise réelle des trades exchange *(livré 2026-08-31)* | ~~🔴~~ | F-01 | `tasks/sync_exchanges.py` (~257,282,338,394,452,521,585,639,809,861), `services/exchanges/*` | Toutes les `Transaction` de la sync sont `currency="EUR"` en dur alors que le `price` vient de paires USD/USDT. → Détecter la quote currency de chaque paire ; stocker `currency` réelle + `conversion_rate` = taux EUR/USD à la **date d'exécution** (le moteur FIFO sait exploiter `fx_rate`). Script de migration pour re-traiter l'historique. | Un achat `BTCUSDT` produit un coût de base en EUR exact (±0,1 %) ; `avg_buy_price` homogène ; test FIN-TEST #1 vert ; script de backfill idempotent validé sur données synthétiques. | L |
| ❌ **FIN-02** Refonte XIRR (devise + flux) *(déjà traité — mesuré 2026-09-01)* | ~~🔴~~ | F-02, F-03, F-04 | `services/analytics_service.py:1564-1644` | (a) ignore `tx.currency` (suppose tout USD) ; (b) compte `TRANSFER_IN/OUT` comme cash-flows fantômes ; (c) ignore `DIVIDEND`/`INTEREST`. → Lire `tx.currency` ligne à ligne (même pipeline que `metrics_service`) ; exclure les transferts internes ; ajouter dividendes+intérêts comme flux entrants. | ✅ Les 3 griefs sont traités dans `analytics_math.py`. Exposition réelle mesurée : **0 transaction non-EUR, 0 dividende**. XIRR = 11,51 %. | M |
| ✅ **FIN-03** Coût de base des transferts non appariés *(traité 2026-08-31 — voir NEW-09/NEW-10 : la cause n'était pas le FIFO)* | ~~🟠→P0~~ | F-06 | `services/metrics_service.py:155-161,720-758`, `transfer_service.py:114-148` | Un `TRANSFER_IN` sans transit apparié crée une couche à **coût zéro** → P&L latent massivement surévalué. Règle divergente entre CUMP et FIFO. → À défaut d'appariement, utiliser `source_asset.avg_buy_price` ; unifier la règle entre les deux moteurs. | Un transfer_in non apparié n'apparaît jamais à coût zéro ; CUMP et FIFO donnent le même P&L (test dédié) ; couverture du cas « sync partielle ». | M |
| ✅ **FIN-04** Service de taux de change robuste *(complété 2026-09-01)* | ~~🟠~~ | F-05, A02 | `services/price_service.py:218-238`, `services/metrics_service.py:388-391,402,1325,1524` | Taux de repli figés en dur (`0.92`/`1.09`) + `except: pass` qui avalent les échecs forex → valorisation silencieusement fausse. → Un seul service de taux : dernière valeur connue **persistée** (pas une constante), TTL court, flag `forex_stale` propagé jusqu'à l'UI ; remplacer les 3 swallow par log + flag `partial`. | ✅ Service unique, table ECB persistée, `forex_stale` propagé, 0 `except: pass` — déjà en place. **Deux manques comblés** : les taux n'étaient rafraîchis qu'à l'occasion d'une sync (→ tâche Celery quotidienne), et les frais payés en crypto n'étaient pas convertis (un `fee_currency` erroné aurait affiché ~19 700 € de frais). | M |
| ✅ **FIN-TEST** Tests numériques de référence *(vérifié 2026-09-01 : déjà fait)* | ~~🔴~~ | §3 rapport 01 | `backend/tests/unit/` | Les tests « parity/xirr » actuels ne vérifient **aucune valeur numérique** (XIRR juste borné `[-95,1000]`, parité tolérée à 1 %). → Ajouter des tests unitaires purs avec valeurs attendues : coût de base multi-devises, XIRR golden (10 000€→11 000€/1 an = 10 %), exclusion transferts, div/intérêts, transfer zéro-coût, forex périmé. | ≥ 7 nouveaux tests unitaires déterministes (sans Docker/HTTP) ; tournent en CI ; chacun mappé à un finding FIN-xx ; parité resserrée à < 0,5 %. | M |

---

## EPIC B — Navigation & vérité produit (P0/P1)

| Ticket | Prio | Sév. | Source | Fichiers | Problème → Correctif | Critères d'acceptation | Effort |
|--------|------|------|--------|----------|----------------------|------------------------|--------|
| ✅ **UX-01** Menu « Stratégies » → 404 *(livré 2026-08-31)* | ~~P0~~ | ~~🔴~~ | F-01(UX) | `components/layout/NavRail.tsx:67`, `App.tsx` | `/strategies` n'a ni route ni redirect → 404. → Ajouter `<Route path="strategies" element={<Navigate to="/intelligence?tab=strategies" replace/>}/>` (ou pointer le menu directement). | Clic « Stratégies » n'atteint jamais la 404 ; test e2e de navigation menu. | XS |
| **UX-02** Triple titrage des onglets | P1 | 🔴 | F-02(UX) | `IntelligencePage`, `PortfolioUnifiedPage`, `StrategyPage`, pages internes | Breadcrumb + label d'onglet + `<h1>` répètent le même mot. → Prop `embedded` sur les pages internes qui masque leur `<h1>` quand montées dans un conteneur. | Aucune page d'onglet n'affiche un titre dupliqué ; le titre unique vit dans le conteneur. | S |
| **UX-03** Promesses d'actifs inexistants + onboarding mal monté | P1 | 🔴/🟠 | F-03, F-04(UX) | `components/OnboardingWizard.tsx:35-48,93-96`, `pages/ReportsPage.tsx:354-369`, `DashboardPage.tsx:492` | Onboarding/Rapports vendent actions/ETF/immobilier/SCPI (absents) ; le wizard n'est monté que sur `/crypto`, jamais sur `/`. → Aligner sur crypto+crowdfunding ; remonter le wizard au `Layout` (ou `/`). | Plus aucune mention d'actif non géré ; un nouveau compte voit l'onboarding dès `/`. | S |

---

## EPIC C — Robustesse backend (P1)

| Ticket | Sév. | Source | Fichiers | Problème → Correctif | Critères d'acceptation | Effort |
|--------|------|--------|----------|----------------------|------------------------|--------|
| ✅ **ARC-01** Boucle async / engine Celery *(livré 2026-09-01)* | ~~🔴~~ | A01, C06 | `core/database.py:14`, `tasks/*` (7 fichiers `new_event_loop`) | Engine async créé une fois au niveau module, réutilisé par des boucles recréées à chaque tâche → « Future attached to a different loop », fuites de pool. → Un seul helper `run_async` dans `tasks/__init__.py` + engine worker en `NullPool` (ou `asyncio.run` partout). | ✅ 1 seul helper (`tasks/async_runner.py`), 0 duplicata. Engine en `NullPool` sous Celery. **Attention** : une première version appelait `set_event_loop(None)` dans le `finally`, ce qui retirait la boucle de l'appelant et cassait 103 tests. | M |
| ❌ **ARC-02** Relations ORM + eager loading *(infondé — mesuré 2026-09-01)* | ~~🟠~~ | B03 | tous les `models/*.py`, endpoints lourds | `relationship()` = 0 partout ; jointures FK manuelles ; aucun `selectinload` → N+1. → Déclarer les relations clés (portfolio→assets→transactions) avec `lazy="selectin"`. | Relations déclarées sur les 5 modèles centraux ; dashboard/portfolio sans N+1 (compteur de requêtes en test) ; pas de régression de valeur. | L |
| **ARC-03** Sortir la logique des god-endpoints | 🟠 | B02 | `endpoints/transactions.py` (70 req.), `dashboard.py` (37), `api_keys.py` (59) | Logique métier + SQL dans les endpoints → non réutilisable par Celery, non testable hors HTTP. → Extraire `transaction_service.py`, `api_key_service.py` ; l'endpoint = validation + appel service + mapping. | Endpoints réduits au routing ; logique couverte par tests de service ; réutilisée par au moins une tâche. | L |
| **ARC-04** Factoriser `_classify_and_mark_error` | 🟠 | B04 | `tasks/sync_exchanges.py:39`, `endpoints/api_keys.py:27` | Fonction dupliquée à l'identique. → `services/exchange_error_classifier.py` importé des deux côtés. | 1 seule implémentation ; les deux appelants l'importent ; test unitaire de classification. | XS |

---

## EPIC D — États d'erreur & cohérence UX (P1/P2)

| Ticket | Prio | Sév. | Source | Fichiers | Problème → Correctif | Critères d'acceptation | Effort |
|--------|------|------|--------|----------|----------------------|------------------------|--------|
| 🟢 **UX-04** États d'erreur React Query *(14/17 pages — 2026-09-01)* | P1 | 🟠 | F-06(UX), B07 | `frontend/src/pages/*` — **restent** `ExchangesPage`, `ReportsPage`, `SettingsPage` | Échec API → écran vide/spinner infini (le RouteErrorBoundary ne capte pas les queries en erreur). → Composant `<QueryErrorState onRetry={refetch}/>` + convention « toute `useQuery` rend un état d'erreur ». | Composant créé ; branché sur ≥ pages critiques (dashboard, portfolio, transactions, exchanges, intelligence) ; test simulant un 500. | M |
| **UX-05** Taxonomie Stratégie/Stratégies/Objectifs | P2 | 🟠 | F-05(UX) | routes + `ReportsPage` RebalancingTab | 3 emplacements, noms quasi identiques (`strategy` vs `strategies`). → « Objectifs » (`/goals`) + « Stratégies de rebalancing » (route unique) ; supprimer/relier le doublon RebalancingTab. | Un seul emplacement par concept ; URLs sans collision singulier/pluriel. | M |
| **UX-06** Consolidation onglet Intelligence | P2 | 🟠 | F-05, tableau redondance | `IntelligencePage` (6 onglets) | Insights/Smart Insights/Analyses quasi-synonymes ; Stratégies mal classée sous « Analyses IA ». → Regrouper les 3 insights ; sortir Stratégies. | ≤ 4 onglets cohérents ; labels métier explicites (« Signaux Alpha » vs « Diagnostic portefeuille »). | M |
| **UX-07** Corrections de navigation diverses | P2 | 🟡 | F-07,F-08,F-10,F-11,F-12(UX) | `MasterDashboardPage:578`, `Breadcrumb.tsx`, `CrowdfundingMesProjectsPage:36`, `ReportsPage:315` | Raccourci « Signaux Alpha » → mauvais onglet ; breadcrumb non cliquable ; breadcrumb crowdfunding figé ; onglet Rapports non synchronisé à l'URL ; dashboards jumeaux. → Lot de corrections ciblées. | Chaque sous-point vérifié individuellement (deep-link onglet, breadcrumb cliquable, cible raccourci correcte). | M |
| **UX-08** Skeletons vs spinners | P2 | 🟡 | F-09(UX) | 29 pages en `Loader2` plein écran | Saut de mise en page + perception de lenteur. → Skeletons sur les écrans à structure connue (tables, KPI rows). | Pages à structure fixe en skeleton ; pas de layout shift mesuré. | M |

---

## EPIC E — Durcissement sécurité (P1/P2)

| Ticket | Prio | Sév. | Source | Fichiers | Problème → Correctif | Critères d'acceptation | Effort |
|--------|------|------|--------|----------|----------------------|------------------------|--------|
| ✅ **SEC-01** Secret webhook Telegram obligatoire en prod *(livré 2026-09-01)* | ~~P1~~ | ~~🟠~~ | H-01 | `endpoints/telegram_webhook.py:54-57` | Vérif conditionnelle : sans secret en prod, webhook non authentifié. → Échouer au démarrage (ou 403 systématique) si `is_production and bot_enabled and not TELEGRAM_WEBHOOK_SECRET`. | En prod sans secret : le bot ne démarre pas / webhook 403 ; test de config. | S |
| ✅ **SEC-02** Ne plus fuiter les exceptions au client *(livré 2026-09-01)* | ~~P1~~ | ~~🟠~~ | H-02 | `endpoints/api_keys.py:~1404-1407,~1601-1604` | `f"...{type(e).__name__}: {e}"` renvoyé au client. → Logger l'exception complète côté serveur, message générique au client (comme `system.py`). | Aucune réponse client ne contient de détail d'exception ; logs serveur conservent le détail. | XS |
| ✅ **SEC-03** Énumération de comptes au register *(réel — mesuré 2026-09-01)* | P2 | 🔵 | M-01 | `endpoints/auth.py:145-149` | Confirme l'existence d'un email. → Message générique / 201 neutre, comme forgot/resend. | `/register` ne distingue plus email existant vs nouveau. **Sévérité abaissée 🟡→🔵** : 1 seul utilisateur en base, l'oracle ne révèle que l'adresse du propriétaire. À faire pour la cohérence avec forgot/resend, qui sont déjà neutres. | XS |
| ⚠️ **SEC-04** Durcissements config *(1 sous-point sur 3 — mesuré 2026-09-01)* | P2 | 🟡 | M-03,M-04,M-05 | `main.py` (admin_fix_mirrors), `core/rate_limit.py:10-19`, `core/config.py:125-127` | Dump debug admin verbeux ; `X-Forwarded-For` spoofable ; Redis TLS `CERT_NONE`. → Réduire le log admin (compteurs) ; ne lire XFF que derrière proxy de confiance (hop Render) ; Redis `CERT_REQUIRED` + CA Upstash. | ✅ XFF non spoofable (lecture depuis la droite) et ✅ Redis en TLS vérifié **étaient déjà faits**. **Reste** : `admin_fix_mirrors` (232 l.) exécute un `ALTER TABLE` depuis HTTP et renvoie un dump des transactions — c'est le chemin des fantômes Tangem. **→ le supprimer, pas le réduire.** | S |
| 🟢 **SEC-05** Documenter/renforcer fingerprint & fail-open *(partiel — mesuré 2026-09-01)* | P3 | 🔵 | M-02,L-01,L-03,L-04 | `core/security.py:15-21`, `api_keys.py:~1678`, `api/deps.py:155-176`, blocklist Redis | Fingerprint UA-only (faux sentiment de sécurité) ; task_id sans ownership ; fail-open silencieux ; blocklist fail-open si Redis down. → Documenter explicitement les limites ; ajouter `user_id` aux tâches d'import ; stratégie fail-open/closed décidée + alerte Redis. | ✅ Le fail-open **n'est plus silencieux** : décidé, commenté, loggué en WARNING (`deps.py:115`, `auth.py:517`). **Restent** : (a) la docstring du fingerprint surpromet (« preventing stolen tokens from being used in a different browser » — un UA se recopie) ; (b) alerte Redis absente. L'IDOR sur `import-status` est réel mais **non exploitable** (`task_id` = `uuid4`). | S |
| ❌ **SEC-06** Migration `python-jose` → `pyjwt` (veille) *(périmé — mesuré 2026-09-01)* | P3 | 🔵 | §3 rapport 04 | `requirements.txt` | `python-jose` peu maintenue ; `bcrypt==4.0.1` ancien. → Évaluer migration `pyjwt`, surveiller bcrypt. | `python-jose` est en **3.4.0**, la version qui corrige les CVE citées (elles visent ≤ 3.3.0), et `algorithms=[…]` est imposé aux deux `jwt.decode`. Reste `bcrypt==4.0.1` : **`passlib` n'étant pas installé**, l'obstacle habituel à la montée (passlib / bcrypt ≥ 4.1) n'existe pas. | XS |

---

## EPIC F — Dette structurelle / god-files (P2)

| Ticket | Sév. | Source | Fichiers | Problème → Correctif | Critères d'acceptation | Effort |
|--------|------|--------|----------|----------------------|------------------------|--------|
| ✅ **ARC-05** Découper `prediction_service.py` *(livré 2026-09-01)* | ~~🟠~~ | B01 | `services/prediction_service.py` (**2 416 → 1 655 LOC** ; l'audit annonçait 3 733) | God-file : prédiction + régime + sentiment + anomalies + cache + accuracy. → Découper en `forecasting/`, `regime/`, `sentiment/`, `accuracy/` (la couche `ml/` existe déjà). | 🟢 761 lignes extraites (`prediction_alpha.py`, 800 LOC). La cible « aucun fichier > 800 LOC » n'est pas atteinte : le service reste à 1 655 lignes. Aucune régression (1 208 tests verts). | L |
| **ARC-06** Découper les god-services secondaires | 🟡 | C04 | `report_service.py` (2744), `metrics_service.py` (2127), `analytics_service.py` (2111) | Mêmes risques à moindre échelle. → Découpage progressif calcul/agrégation/formatage. | Réduction mesurable de la taille ; tests conservés verts. | L |
| 🟢 **ARC-07** Découper `ExchangesPage.tsx` *(entamé 2026-09-01)* | 🟠 | B06 | `pages/ExchangesPage.tsx` (**1 368 → 1 286 LOC** ; l'audit annonçait 2 185) | Monolithe (dialogs, formulaires, tables, sync, cold wallets). → `ApiKeyForm`, `ApiKeyList`, `SyncStatusCard`, `ColdWalletSection` + hooks. | ⚠️ Non atteint volontairement : `ExchangeLogo` et les types sont sortis, **le découpage large est différé jusqu'à ce que la page ait des tests de rendu** — sans eux, un refactor de cette ampleur casse en silence. | L |
| **ARC-08** Trancher le doublon insights | 🟠 | B05 | `services/insights_service.py` (403) vs `smart_insights_service.py` (1525) + endpoints | Deux systèmes parallèles, recouvrement probable. → Confirmer le vivant, déprécier/supprimer l'ancien. | Une seule source de vérité insights ; code mort supprimé. | M |
| **ARC-09** Unifier les `queryKey` | 🟡 | C03 | ~14 clés hardcodées (`charts/*`, `PlatformSelect`, `DashboardMunitionsCard`) | Contournent `lib/queryKeys.ts` → invalidation incohérente, caches périmés. → Migrer toutes les clés vers la factory. | 0 `queryKey` hardcodé ; invalidation testée. | S |
| **ARC-10** Stratégie librairies de charts | 🟡 | C01 | `frontend/package.json:17-21,45` | `@nivo/*` **et** `lightweight-charts`. → Choisir par cas d'usage et documenter, ou consolider ; retirer la lib non utilisée. | Décision documentée ; bundle allégé si retrait. | S |
| **ARC-11** Centraliser le formatage monétaire | 🟡 | C05 | **13 fichiers** formatent les montants à la main (l'audit en annonçait 43) | Formatage dispersé → incohérences devise/décimales. → Tout passer par `lib/utils.formatCurrency`. | 1 seul point de formatage ; cohérence visuelle vérifiée. | M |

---

## EPIC G — Accessibilité (P2)

| Ticket | Sév. | Source | Problème → Correctif | Critères d'acceptation | Effort |
|--------|------|--------|----------------------|------------------------|--------|
| **A11Y-01** `aria-label` sur tous les boutons icône | 🟠 | A-01 | 29 boutons `size="icon"` à auditer. → Label sur chaque (suppression, refresh, fermeture…). | 0 bouton icône sans nom accessible (axe-core). | M |
| **A11Y-02** `prefers-reduced-motion` sur framer-motion | 🟠 | A-02, F-15 | Animations JS (Master, Login) non couvertes. → Brancher `useReducedMotion()` sur les `motion.*`. | Avec reduced-motion actif : aucune entrée animée JS. | S |
| **A11Y-03** Cibles tactiles & labels rail | 🟡 | A-04, A-03, F-16 | Boutons `h-7`/`h-8` < 44 px ; labels du rail visibles au hover seulement. → Padding tactile ≥ 40 px ; `group-focus-within:opacity-100`. | Cibles ≥ 40 px sur mobile ; labels visibles au focus clavier. | S |
| **A11Y-04** Contrastes secondaires | 🔵 | A-05 | `--gain` light & `text-muted-foreground/70` possiblement < 4.5:1. → Vérifier au contrastomètre, remonter la luminance si besoin. | Tous les textes ≥ 4.5:1 (4.5 normal / 3:1 large). | S |

---

## EPIC H — Polish & faible sévérité (P3)

| Ticket | Source | Correctif | Effort |
|--------|--------|-----------|--------|
| ❌ **FIN-05** Corriger la docstring de signe `_xirr` *(déjà correct — vérifié 2026-09-01)* | F-08 | Refléter la convention réelle (négatif = sortie). | XS |
| **FIN-06** Découpler les tirages Monte Carlo | F-09 | Graines distinctes ou re-tirage proba/ETA ; afficher un intervalle. | S |
| **FIN-07** Mois restants via `relativedelta` | F-10 | Remplacer `delta/30.44` par mois calendaires exacts. | XS |
| **FIN-08** `Decimal` pour montants advisory affichés | F-11 | Cashflows stress test / DCA affichés au centime en `Decimal`. | M |
| **FIN-09** Appariement remboursement par date+montant | F-12 | Pondérer la réconciliation ; documenter l'arrondi « last installment ». | S |
| **FIN-10** Centraliser conversion prix actions | F-13 | `price_service.get_price` renvoie toujours en devise demandée. | S |
| **FIN-11** Logguer le clamp XIRR | F-14 | Alerter quand `[-95,1000]` s'active au lieu de borner en silence. | XS |
| **FIN-12** Hash dédup avec heure | F-15 | Inclure l'heure / `external_id` pour ne pas fusionner 2 DCA identiques le même jour. | S |
| **FIN-13** Earn/wrapped par table explicite | F-16 | Remplacer le strip de préfixe `W` par une table de variantes connues (évite WIF/WLD cassés). | S |
| ❌ **ARC-12** Supprimer l'alias mort `fetchUser` *(infondé : utilisé par `VerifyEmailPage` — 2026-09-01)* | D02 | `authStore.ts` — retirer l'alias inutilisé. | XS |
| **ARC-13** Épingler les deps critiques | C02 | Pin strict react-query/axios/zod (au-delà du lockfile). | XS |
| **UX-09** `font-serif` sur h1 du Login | F-13(UX) | Cohérence de marque dès l'entrée. | XS |
| **UX-10** Remplir le Header | F-14(UX) | Breadcrumb/titre courant + recherche globale (cmd-K déjà présent). | S |
| **UX-11** Crowdfunding Audit Lab : onglet ou route | F-17(UX) | Trancher l'asymétrie onglets vs route dédiée. | S |

---

## VÉRIFICATION (transverse)

| Ticket | Prio | Problème → Action | Critères d'acceptation | Effort |
|--------|------|-------------------|------------------------|--------|
| **VERIF-01** Audit design **rendu** (pas le code) | P1 | Le 8,5/10 design est non vérifié (lu dans le CSS, pas regardé). → Rendre l'app en local (build + Claude_Preview), capturer chaque écran clé en dark **et** light, à 375/768/1024/1440 px, et juger visuellement : hiérarchie, hardiesse réelle, cohérence, identité vs template. | Captures de tous les écrans clés ; verdict design **fondé sur le rendu** ; findings visuels ajoutés au backlog. | M |
| ✅ **VERIF-02** Quantifier l'impact FIN-01/02 *(fait 2026-08-31)* | ~~P1~~ | **Mesuré sur les données réelles.** Dev : 282,86 € de base comptés en EUR à tort → 246,52 € corrigés, soit −36,34 € (−12,85 %), avec des taux historiques distincts (0,95557 en 03/2025 · 0,87025 en 11/2025 · 0,85734 en 01/2026). Prod : **0 ligne concernée** — les 164 achats/ventes sont réellement en EUR. → *L'estimation « 8-9 % pour la majorité des traders » ne se vérifie pas sur ce compte.* | Rapport chiffré produit, avant/après, sur données réelles plutôt que synthétiques. | S |

---

## « Definition of Done » par domaine (cible réaliste, pas un chiffre rond)

- **Calculs financiers** : EPIC A + FIN-TEST livrés ; parité dashboard↔XIRR↔rapports < 0,5 % ; tous montants en `Decimal` sur les chemins affichés ; aucun taux en dur ; `forex_stale` visible. → *score défendable seulement une fois les tests de référence verts.*
  - **2026-08-31** : FIN-01 et FIN-03 livrés ; invariant `check_holdings_qty` à **0 violation matérielle** (était 11), code retour 0 ; P&L Crypto rétabli à +252 € ; **1146 tests** backend verts et **CI verte pour la première fois depuis ≥ 11/07**. Restent FIN-02 et FIN-04 — à cadrer sur mesure d'exposition, pas sur l'estimation de l'audit. FIN-03 livré (NEW-09/NEW-10). Restent FIN-02 et FIN-04 — à cadrer sur mesure d'exposition, pas sur l'estimation de l'audit.
- **Architecture & code** : ARC-01→04 livrés ; aucun fichier > ~800 LOC sur les god-files traités ; relations ORM sur les modèles centraux ; 0 `except: pass` sur du calcul financier.
- **Fonctionnalités & UX** : EPIC B + UX-04 livrés ; 0 lien mort ; états d'erreur sur toutes les pages critiques ; promesses produit alignées sur le périmètre réel ; **VERIF-01 effectué**.
- **Sécurité** : 0 finding 🟠 ouvert (SEC-01/02) ; durcissements SEC-04 ; **+ processus continu** : veille CVE (npm/pip audit en CI), rotation de clés, alerte Redis. La sécurité n'est jamais « finie ».
