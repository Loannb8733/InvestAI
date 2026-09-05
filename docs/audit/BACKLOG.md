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

5. **Les tests verts ne disent rien du rendu.** 160 tests front passaient pendant qu'un
   rail affichait « CROW » au clavier, qu'une page n'avait aucun `<h1>`, qu'un titre
   annonçait « Wealth Journey » au lieu d'« Objectifs » et qu'une requête mettait 92
   secondes. Une assertion sur le DOM ne voit ni une largeur CSS, ni un temps de
   réponse, ni une incohérence de vocabulaire. **Regarder l'app est une étape
   distincte, pas une redondance.**

6. **Un correctif n'est livré que sur tous ses points d'appel.** FIN-07 a été corrigé le
   2026-09-03 dans `goal_projection_service`, ticket clos. Le 2026-09-05, `endpoints/goals.py`
   calculait toujours le **même chiffre** avec l'ancienne formule — et l'affichait sous le
   même libellé. Deux écrans, deux résultats, sur 99,5 % des échéances. Avant de clore un
   ticket de calcul : chercher le concept, pas le fichier. Ici, un `grep 30.44` de dix
   secondes aurait suffi.

Corollaire sur les tests : deux tests écrits ce jour-là passaient au vert **sans rien
vérifier** — l'un cherchait `executed_at` et trouvait le mot dans un commentaire voisin.
Tout test de non-régression doit être validé par un canari : casser volontairement le code
et vérifier que le test échoue. C'est exactement le reproche que ce backlog fait aux tests
parity/XIRR (FIN-TEST).

### État au 2026-09-01 — 27 tickets mesurés sur 50

Ce tableau dit ce qui a été **vérifié dans le code**, et ce qui ne l'a pas été. Un ticket
non mesuré n'est ni vrai ni faux : il n'a pas été regardé. Vu que **11 des 27 tickets
vérifiés se sont révélés infondés, périmés ou déjà faits**, aucun des 23 restants ne
devrait être engagé sans mesure préalable.

| EPIC | Mesurés | Livrés | Infondés / périmés / déjà faits | Jamais mesurés |
|---|---:|---|---|---|
| **A** — Exactitude financière | **5/5** | FIN-01, FIN-03, FIN-04 | FIN-02, FIN-TEST | — |
| **B** — Navigation & vérité produit | **2/3** | UX-01 | — | UX-02 |
| **C** — Robustesse backend | **3/4** | ARC-01 | ARC-02 | ARC-04 |
| **D** — États d'erreur & UX | **3/5** | UX-04 (17/17), UX-05 | — | UX-06, UX-07 |
| **E** — Sécurité | **6/6** | SEC-01→05 | SEC-06 | — |
| **F** — God-files | **4/7** | ARC-05, ARC-07 (partiel), ARC-11 | ARC-09 (quasi fait) | ARC-06, ARC-08, ARC-10 |
| **G** — Accessibilité | **4/4** | A11Y-01→04 | — | — |
| **H** — Polish | **3/14** | — | FIN-05, ARC-12 | FIN-06→13, ARC-13, UX-10, UX-11 |
| **VÉRIF** | **2/2** | VERIF-02, **VERIF-01** (32 écrans / 32) | — | — |
| **Total** | **32/50** | 18 | 6 | 18 |

UX-03 et UX-08 (mesurés réels, non traités) et UX-09 (polish réel) comptent dans les
mesurés de leur EPIC sans figurer ci-dessus : ils sont vérifiés mais ni livrés ni
écartés.

**Tout a été regardé.** Les 50 tickets ont désormais un verdict fondé sur le code, non
sur le texte de l'audit. (**UX-02 est confirmé** par le cas « Wealth Journey ».)

**L'angle mort a été levé** : l'app a été parcourue à l'écran le 2026-09-01 (voir
« VERIF-01 — ce que le rendu a appris »). Trois défauts vivaient dans l'interface pendant
que 160 tests étaient verts, et une lenteur de 92 s (NEW-13) qu'aucun ticket ne
mentionnait. Le 8,5/10 de design reste néanmoins une hypothèse : 7 écrans sur 32.

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
| **NEW-14** | 🟡 | **`update_all_prices` cassait sur « Task attached to a different loop »** : elle appelait en direct trois tâches faisant chacune leur `run_async`, alors que l'engine async garde ses connexions liées à la première boucle. Défaut latent (la tâche n'est pas planifiée). **Un second bug se cachait derrière** : une fois la boucle unifiée, `price_service.get_exchange_rate(...)` s'est révélé ne jamais avoir existé — la méthode s'appelle `get_forex_rate`. L'`AttributeError` était rattrapée par le `except` voisin : la tâche rapportait « 0 mis à jour » sans rien tenter. Changes : **0 → 6**. | ✅ corrigé |
| **NEW-13** | 🔴 | **Deux causes, toutes deux invisibles en lecture rapide.** (1) `Semaphore(5)` annulait l'espacement des appels CoinGecko ; (2) la tâche Celery qui pré-charge l'historique écrivait dans des clés que personne ne lisait. **`/predictions/market-cycle` répondait en 65 s à 92 s**, le bandeau de régime restant en squelette pendant tout ce temps. **Ma première explication était fausse** : ni le nombre d'actifs (7, pas 56), ni l'absence de parallélisme (`asyncio.gather` était déjà en place). La cause : `Semaphore(5)` laissait 5 coroutines entrer ensemble dans la section critique, lire le même horodatage et repartir à la même milliseconde — le délai de 1,2 s retardait une rafale sans jamais l'espacer. D'où les 429, puis 10 s + 20 s + 30 s de backoff par symbole, pour finir sans donnée. | ✅ **corrigé** — `Lock`, backoff plafonné, budget de temps partagé, et lecture réconciliée avec le cache Celery |
| **NEW-12** | 🟠 | **Le garde-fou des scripts dangereux ne protégeait pas dans un environnement dégradé.** `require_consent()` était appelé en fin de fichier, donc après `from app.core.database import …`. Or ces scripts font `sys.path.insert(0, "/app")` — le chemin du conteneur. Hors conteneur, l'import échouait sur `ModuleNotFoundError` avant que le garde soit atteint : sortie en code 1, mais sans message et pour la mauvaise raison. **La CI était rouge depuis 6 exécutions** pour cette raison. → Refus remonté au-dessus de tout import applicatif (stdlib seule) + second `sys.path.insert` portable. | ✅ corrigé, CI verte |

**Invariant A (`check_holdings_qty`)** : 11 violations → **0 violation matérielle** (4 avertissements sur des poussières), code retour 0. Vérifié en production.

**P&L du portefeuille Crypto** : +252 € après nettoyage, contre +38 € au plus bas de la session. Contrôle indépendant : le PRU BTC/Kraken calculé tombe sur celui affiché par Kraken (55 544 €).

### VERIF-01 — ce que le rendu a appris (2026-09-01)

L'app a enfin été **regardée**, connectée sur les données réelles, en desktop (1280×800)
et en mobile (390×844). Sept écrans parcourus en détail, treize audités
automatiquement.

**Le constat central : les 160 tests front étaient verts pendant que trois défauts
visibles vivaient dans l'interface.** Aucun n'était détectable autrement qu'en
regardant.

| Trouvé | Nature | État |
|---|---|---|
| **Rail tronqué au clavier** | `group-focus-within:opacity-100` révélait les libellés, mais le rail restait à 76 px : « Crowdfunding » s'affichait « CROW ». Ma correction A11Y-03 était à moitié faite. | ✅ `focus-within:w-64` |
| **`Badge` sans `forwardRef`** | Radix lui passe une ref via `asChild` ; React avertissait, et le tooltip du badge « prix périmé » ne pouvait pas se positionner. | ✅ corrigé |
| **`IntelligencePage` sans `<h1>`** | Aucun titre dans l'arbre d'accessibilité, hiérarchie démarrant au niveau 2. | ✅ `<h1 class="sr-only">` |
| **« Wealth Journey »** | Le `<h1>` de `/goals` contredisait le menu, le breadcrumb et l'onglet, qui disent tous « Objectifs » — et en anglais. **UX-02 confirmé par l'exemple.** | ✅ corrigé |
| **HMR mort** | `VITE_HMR_DISABLE=true` masquait le problème : port interne 3000 annoncé au navigateur qui doit joindre 3001, plus `allowedHosts: 'all'` (syntaxe Vite 6) qui faisait rejeter le handshake en 400 sous Vite 5. | ✅ réparé |

#### 🔴 NEW-13 — `/predictions/market-cycle` met jusqu'à 92 secondes

**La découverte la plus lourde de la session, et elle ne figure dans aucun ticket.**

Mesuré depuis le navigateur, sur le portefeuille réel (56 actifs) :

| Appel | Durée |
|---|---:|
| 1er (cache froid) | **92 s** |
| 2e (cache chaud) | 1,4 s |
| 3e | **61 s** |

Le cache ne tient pas : le troisième appel repart à une minute. `get_market_cycle`
(`prediction_cycles.py`) boucle **séquentiellement** sur chaque actif du portefeuille et
appelle l'API d'historique quand le cache est froid. Avec 56 actifs et la limite
CoinGecko à 50 requêtes/minute, un rafraîchissement dépasse mécaniquement la minute.

Effet visible : le bandeau de régime de marché reste en squelette pendant tout ce temps,
sur `/intelligence` comme sur `/crypto` (6 squelettes encore affichés après 6 s).

**Non corrigé** — le correctif (mise en cache qui tient, parallélisation bornée, respect
du rate limit) est un chantier à part entière, à mesurer avant d'engager.

#### NEW-13 — corrigé le 2026-09-01

**Un verrou mal dimensionné, pas un problème de volume.** `asyncio.Semaphore(5)` autorisait
cinq entrées simultanées dans la section censée espacer les appels : les cinq coroutines
lisaient le même `_last_coingecko_call`, dormaient la même durée, repartaient ensemble. Le
délai de 1,2 s retardait la rafale au lieu de la sérialiser.

Un `asyncio.Lock` suffit à rétablir l'espacement — et donc à supprimer les 429 :

| Mesure (cache vide) | Avant | Après |
|---|---:|---:|
| Quota disponible | 65 s | **8,5 s** |
| Quota épuisé (pire cas) | 65 s | **13,5 s** |
| Bandeau de régime à l'écran | 92 s | **5,6 s** |

Les résultats sont identiques à l'existant (régime `top` à 0.98, même nombre d'actifs) :
c'est bien de la latence supprimée, pas de l'analyse sacrifiée.

**Deux gardes complètent**, parce qu'un quota journalier peut tomber quoi qu'on fasse :
le backoff 429 est plafonné à 10 s et respecte `Retry-After` (il valait 10 s + 20 s + 30 s),
et les appels externes du cycle de marché ont un budget de 12 s au-delà duquel l'analyse
est rendue partielle plutôt que l'écran figé.

**Une piste essayée puis retirée** : un disjoncteur global sur 429. Mesuré à 0,7 s — mais
sans aucune donnée. Rapide parce que vide n'est pas un progrès ; la comparaison avec le
code d'origine (`git stash`) l'a montré, et c'est elle qui a évité de livrer une fausse
victoire.

**Second temps (même jour) : deux caches qui s'ignoraient.**

Le « déport vers une tâche périodique » n'avait pas à être construit : `cache_historical_data`
tourne **toutes les 30 minutes depuis longtemps**, avec persistance PostgreSQL et une copie
`:fallback` à 24 h. Elle travaillait pour rien.

| Écrit par | Clé | Lu par |
|---|---|---|
| `tasks/history_cache.py` (Celery, 30 min) | `hist:<SYM>_<jours>` | personne, côté analyses |
| `core/redis_client.py` (à la demande, TTL 1 h) | `hist:<sym>:<type>:<jours>` | `prediction_cycles` |

Les deux conventions ne se croisaient jamais. `get_market_cycle` repartait chercher chez
CoinGecko des séries **déjà présentes en Redis**, à quelques octets de là.

`get_cached_history` lit désormais les deux formats, du plus précis au plus large, et
retaille une série annuelle pour une demande plus courte. Aucune écriture dupliquée.

| Mesure (quota épuisé — cas défavorable) | Avant | Après |
|---|---:|---:|
| Cache de la tâche disponible | 65 s | **2,9 s**, et **7 actifs** analysés au lieu de 1 |
| Tout le cache vidé | 65 s | **12,0 s**, régime préservé |
| Bandeau à l'écran | 92 s | **3,3 s** |

**Le budget de temps a été corrigé deux fois en chemin**, et les deux erreurs méritent
d'être notées :

1. appliqué *appel par appel*, il s'additionnait (12 s pour BTC, puis 12 s pour les
   autres) et ne bornait donc rien — il est maintenant partagé par un compte à rebours ;
2. posé sur le `gather`, il **annulait au dépassement les actifs déjà servis par le
   cache** en quelques millisecondes : un seul symbole manquant privait l'analyse de tous
   les autres. Il s'applique désormais par actif.

Deux appels échappaient encore au budget (dominance BTC, prix des stablecoins) : bornés
également. Le pire cas absolu tient enfin la promesse annoncée — 12 s.

**Troisième temps : plus aucun appel réseau d'historique dans le chemin HTTP.**

Tant que `get_market_cycle` pouvait appeler CoinGecko, sa latence restait à la merci d'un
quota. Le module `services/price_history_store.py` lit désormais Redis puis **PostgreSQL**,
sans jamais sortir. Le repli en base compte autant que le cache : après un redémarrage,
Redis est vide et `asset_price_history` contient 367 jours par symbole.

| Mesure (Redis vidé, quota épuisé) | Avant | Après |
|---|---:|---:|
| Durée de l'analyse | 65 s | **0,9 – 1,2 s** |
| Actifs analysés | 1 (souvent 0) | **7** |
| Bandeau à l'écran | 92 s | **1,0 s** |

L'analyse est donc **plus complète en plus d'être plus rapide** : les symboles qui
échouaient en 429 sont servis localement.

Restent trois appels sortants, tous bornés et mesurés sous la seconde : Fear & Greed,
dominance BTC, prix courants. Ces derniers ont leur propre cache et leur propre tâche —
les figer serait un contresens, un prix doit être frais.

**Bilan des trois temps : 92 s → 1,0 s à l'écran.** Et une leçon : la « tâche périodique à
créer » existait déjà ; le travail a consisté à la faire lire, pas à l'écrire.

#### Ce qui a été confirmé à l'écran

- **UX-04** : l'état d'erreur s'affiche réellement (« Impossible de charger vos clés
  API »), le bouton « Réessayer » relance la requête, le cycle complet fonctionne.
- **UX-05** : « Décisions » → `/strategies` → onglet Décisions ; « Objectifs » →
  `/goals` ; `/strategy` redirige ; breadcrumb « Outils › Objectifs ».
- **ARC-11** : « 1 558,08 € », « +351,75 € » — format cohérent partout.
- **A11Y-04** : contraste `--gain` mesuré **par le navigateur** à 4,80:1 sur carte et
  4,67:1 sur fond (mes calculs Python donnaient 4,82 et 4,68).
- **Responsive** : aucun débordement horizontal du document en 390 px.

#### Second passage (2026-09-02) — les 25 écrans restants

Tous les écrans ont été parcourus, en desktop (1280×800) et en mobile (390×844),
onglets et modales compris.

**🔴 Un 500 en production, sur un cas d'usage courant.**
`GET /dashboard?days=0` — l'option **« Tout »** du sélecteur de période — répondait 500 ;
toutes les autres valeurs passaient. La cause n'est pas le calcul mais **le cache** :
l'entrée `days=0` avait survécu à une évolution de `EnhancedDashboardResponse`, qui a
gagné des champs (`active_alerts`, `upcoming_events`, `advanced_metrics`,
`last_updated`…). Le dict relu ne pouvait plus construire le modèle, et l'exception
Pydantic remontait en 500 jusqu'à expiration du TTL.

Le piège **se réarme à chaque ajout de champ au schéma**, et ne frappe que les
utilisateurs dont le cache est chaud — ce qui le rend difficile à reproduire. Un cache
qu'on ne sait plus relire est désormais traité comme un cache absent, avec une trace.

**Accessibilité — 27 éléments sans nom accessible**, tous vérifiés dans l'arbre du
navigateur et non par un heuristique DOM :

| Où | Quoi |
|---|---|
| Tableau des transactions | 21 cases de sélection annonçaient « case à cocher » sans dire laquelle |
| Pilier Décisions | 3 boutons icône (rejeter, supprimer, déplier) |
| Formulaire de transaction | 3 listes déroulantes dont le `<Label>` voisin n'était rattaché à rien |
| Toutes les modales | le bouton de fermeture s'annonçait **« Close »** — seul texte anglais restant |

**Hiérarchie de titres** : `AlertsPage` rendait un second `<h1>` alors qu'elle n'est plus
montée que comme onglet du hub Intelligence. Passée en `<h2>`. Défaut introduit par ma
propre correction de la veille — le `<h1>` que j'avais ajouté au conteneur entrait en
collision avec celui de la page interne.

**Ce qui va bien** : aucun débordement horizontal en 390 px sur aucun écran ; le tiroir
de navigation mobile est correctement `inert` + `aria-hidden` ; la modale d'ajout piège
le focus et porte un titre accessible ; `/admin` redirige bien un non-admin ; les 4
onglets de Rapports, le Journal, le Calendrier, le Crowdfunding, l'Audit Lab et les
Simulations n'ont **rien** à signaler.

#### NEW-15 — `GET /dashboard` à 13,4 s, corrigé le 2026-09-02

**Le diagnostic a écarté les suspects habituels un par un**, et c'est ce qui compte ici :

| Hypothèse | Mesure | Verdict |
|---|---:|---|
| Requêtes SQL trop nombreuses | 30 requêtes, **0,43 s** cumulées | ❌ |
| Appels réseau | **2,47 s** pour 17 requêtes | ❌ |
| Calcul Python bloquant l'event loop | **0 blocage** > 0,4 s | ❌ |
| Attente volontaire | **une seule, de 10 s** | ✅ |

L'attente venait du `Retry-After` de CoinGecko — **introduite par ma propre correction de
NEW-13**, qui avait remplacé un backoff de 60 s par « Retry-After plafonné à 10 s ».
Mieux, mais toujours dix secondes devant un utilisateur.

La bonne distinction n'est pas la durée, c'est **qui attend** :

- une **tâche de fond** n'a personne en face ; l'API demande de patienter, on patiente ;
- une **requête HTTP** a quelqu'un devant l'écran ; le cache et PostgreSQL savent déjà
  répondre, on renonce.

Une `ContextVar` posée par le middleware HTTP porte cette distinction sans faire descendre
un drapeau à travers toute la pile d'appels. Les workers Celery et les scripts n'ont pas le
marqueur et gardent le droit d'attendre — vérifié explicitement.

| Mesure | Avant | Après |
|---|---:|---:|
| Cache vide, quota épuisé | 13,4 s | **2,6 s** |
| Cache chaud | — | **0,01 s** |
| Contenu affiché à l'écran | — | **0,26 s** |

Contenu identique, comparé au code d'origine par `git stash` : mêmes valeurs, mêmes 31
points d'historique.

#### NEW-16 — trois filets de sécurité qui ne fonctionnaient pas (2026-09-02)

Le profilage du dashboard a mis au jour une série cohérente : **des secours qui coûtent le
prix d'un secours sans en rendre le service**.

| Filet | Défaut | État |
|---|---|---|
| Repli PostgreSQL de `get_cached_history` | `run_async` appelé depuis une boucle déjà en cours → exception avalée, coroutine jamais attendue | ✅ corrigé |
| Repli CryptoCompare | 401 systématique : aucune clé, aucun réglage pour en fournir une, en-tête jamais transmis | ✅ corrigé |
| Taux de change pour `fee_currency` crypto | 65 transactions paient leurs frais en PAXG, OM, USDC… chacune déclenchait un `latest/PAXG` en 404 | ✅ corrigé |

**Le repli PostgreSQL est le plus sérieux.** `get_cached_history` est synchrone et appelée
par `snapshot_service`, `metrics_service` et `analytics_service` — tous dans une boucle
d'événements. On ne démarre pas une boucle dans une boucle : le filet rendait `[], []` en
silence. Mesuré : **91 prix depuis un script, 0 depuis un endpoint**. Il ne se déclenchait
que là où on n'en avait pas besoin. Une lecture SQL synchrone supprime la question.

**Pour les devises**, la garde est posée dans `get_forex_rate` elle-même, donc elle protège
aussi les appelants futurs. Liste blanche et non liste noire : une monnaie oubliée se
rajoute, un symbole crypto oublié repartirait en appel inutile.

**Reste ouvert, mesuré :**

- ~~`index_comparison` absent~~ — ❌ **mon constat était faux**. Vérifié le 2026-09-02 :
  la réponse contient bien ses 3 entrées (Bitcoin, Ethereum, Solana, avec leurs
  variations). Je l'avais mesuré au moment où le quota CoinGecko était épuisé, donc où la
  liste était temporairement vide. **Une dégradation passagère lue comme une panne
  permanente** — le même travers que la session a déjà rencontré trois fois ;
- `coins/mantra-dao/market_chart` répond 404 quand `simple/price` répond 200 : CoinGecko a
  retiré l'historique de ce coin. L'actif OM est soldé et le dashboard filtre déjà les
  actifs à quantité nulle — **l'appel vient donc d'un autre chemin, non identifié**.
  Changer le mapping serait hasardeux : les deux identifiants candidats donnent des prix
  à un ordre de grandeur d'écart.

#### Quatre faux positifs de mon propre audit

À consigner, parce qu'ils invitent à se méfier des heuristiques DOM maison :

- un interrupteur « sans nom accessible » sur `/alerts` : le navigateur le nomme
  correctement (« Activer les notifications Telegram ») via son `<label for>` ;
- `/crypto` « sans `<h1>` » : le titre existe, mon audit l'avait mesuré pendant le
  chargement ;
- « 9 squelettes bloqués » sur `/crypto` : **tous décoratifs** — `animate-pulse` sert
  aussi au point clignotant du badge « Live », pas seulement aux squelettes ;
- « 7 textes tronqués » sur `/crowdfunding` : des éléments `sr-only`, larges de 1 px
  **exprès**, destinés aux lecteurs d'écran.

**Se fier à l'arbre d'accessibilité du navigateur, pas à un `querySelectorAll` maison.**

#### Le 8,5/10 de design

Toujours pas un verdict — 7 écrans sur 32, desktop et mobile, sans regard de designer
professionnel. Première impression honnête : l'app est **plus soignée que l'audit ne le
laissait croire** — serif assumé sur les titres, chiffres tabulaires, hiérarchie lisible,
thèmes clair et sombre tous deux aboutis. Ce n'est pas un thème sombre paresseux.

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
| **SEC-03** | ✅ | `/register` répond la même chose que l'adresse soit libre ou prise. Le mot de passe est **haché dans les deux branches** : ne le faire que pour une adresse libre rendrait la réponse ~250 ms plus lente et rétablirait l'oracle au chronomètre. Le titulaire d'une adresse déjà inscrite est prévenu par email (best-effort). |
| **SEC-04** | ✅ | `POST /api/v1/admin/fix-mirrors` **supprimé** (232 l.). Doublon manuel de `_create_missing_transfer_mirrors()`, qui tourne déjà à chaque démarrage sous verrou et de façon idempotente : aucune capacité perdue. Il exécutait un `ALTER TABLE` depuis HTTP, renvoyait un dump des transactions, et son `except` renvoyait `str(e)` — la fuite corrigée par SEC-02. |
| **UX register** | ✅ | Défaut adjacent trouvé en corrigeant SEC-03 : le front ne traitait ni `access_token` ni `email_verification_required=false`, donc l'écran d'inscription restait **muet après un succès** — ni toast, ni redirection. |
| **EPIC G** | ✅ | Les 4 tickets d'accessibilité, **le premier EPIC où l'audit tombe juste partout** — mais aucun n'avait l'ampleur annoncée et deux visaient à côté. 9 boutons icône muets nommés ; `MotionConfig` à la racine plutôt que 40 gardes individuels ; libellés du rail visibles au clavier ; contrastes chiffrés et corrigés. |
| **UX-04 (fin)** | ✅ | Les 3 dernières pages, chacune selon ce que sa requête empêche réellement. **`SettingsPage` cachait un défaut plus grave que l'état d'erreur manquant** : les 3 champs du profil restent vides quand la lecture échoue, et la sauvegarde envoie `null` pour tout champ vide — un clic sur « Enregistrer » effaçait TMI, profil de risque et DCA, silencieusement. Le formulaire est donc masqué, pas seulement signalé. Sur `ReportsPage`, à l'inverse, un état d'erreur de page aurait été une **régression** : la liste des années a un repli et tous les rapports restent générables. |
| **UX-05** | ✅ | L'onglet `strategies` d'Intelligence **n'existe plus** depuis la refonte de juillet : le menu « Stratégies » menait à un onglet supprimé via deux redirections. `/goals` devient canonique, l'entrée est renommée « Décisions ». |
| **ARC-11** | ✅ | 4 fichiers migrés. `CalendarPage` affichait « 1 234 EUR » là où le reste de l'app affiche « 1 234,00 € » — même donnée, deux rendus. |
| **SEC-05** | ✅ | 4 fail-open de révocation passés en **ERROR** (préfixe `SECURITY:`) — dont 2 hors ticket, au logout. Ownership vérifié sur `import-status`, avec la même 404 qu'une tâche absente. Docstring du fingerprint réécrite : un User-Agent voyage en clair avec le token qu'il prétend protéger. |
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

#### FIN-09 — un mauvais rapprochement ne se voit pas

Deux échéances proches dans le calendrier se départageaient sur quelques jours, alors que
leurs montants les distinguent franchement. Et l'erreur est silencieuse : l'échéance est
marquée soldée, le tableau de bord affiche un remboursement de plus, et rien ne cloche
avant la fin du prêt — quand une échéance reste ouverte sans raison.

**Note de méthode** : mes premiers tests rejouaient la logique de rapprochement dans une
copie locale. Ils seraient restés verts si le service avait changé. Le score est devenu une
méthode publique pour qu'ils éprouvent l'implémentation utilisée en production — c'est le
même travers que les tests « qui ne vérifient rien » relevés au début de la mission.

#### UX-09 — et une promesse fausse sur le premier écran

Le titre du Login était le seul de l'application hors serif. Sa page jumelle, `Register`,
l'était déjà exactement au même endroit : ce n'était pas un parti pris, c'était un oubli.

**Trouvé en passant, plus gênant que le ticket** : la page annonçait « Actions » parmi ses
univers, dans les pastilles comme dans l'accroche. Même promesse sans parcours que celle
corrigée dans le guide de démarrage — sauf qu'ici, c'est la toute première chose qu'un
visiteur lit.

**Erreur de méthode à consigner** : j'ai poussé ce correctif avec un test rouge.
`LoginPage.test.tsx` attendait la pastille « Actions » ; je n'ai pas regardé la suite front
avant de committer. Rattrapé au commit suivant, mais la vérification aurait dû précéder.

#### FIN-07 — un écart rare, mais qui gonfle l'effort demandé

`int(jours / 30,44)` se trompait d'un mois dans **3 % des échéances possibles** — 118 cas
sur 3 621, mesurés d'un mois à dix ans.

Ce chiffre divise le montant restant à rassembler : un mois de moins, c'est un effort
mensuel plus élevé. Sur une échéance courte, deux mois au lieu de trois demandent **50 %
de plus** que nécessaire — et c'est le nombre que l'utilisateur lit pour décider combien
épargner.

Note de méthode : mon premier commentaire disait « sous-estimait presque toujours ». La
mesure a donné 3 %. Le commentaire porte maintenant le chiffre plutôt que l'impression.

**Suite, le 2026-09-05 — le correctif n'avait couvert qu'un des deux points d'appel.**
`endpoints/goals.py` calculait encore les mois restants en `jours / 30,44` pour produire
le **même chiffre**, affiché sous le même libellé (« X €/mois nécessaire »). Deux écrans,
deux méthodes, un seul nombre aux yeux de l'utilisateur.

Mesure sur 3 652 échéances : les deux chemins divergent dans **99,5 % des cas**. L'écart
médian reste sous 1 %, mais il devient absurde à l'approche du terme, où le diviseur passe
sous l'unité — à un jour de l'échéance, 0,03 mois transformait 10 000 € restants en
« **304 400 €/mois nécessaire** ». Le `min(..., 9 999 999.99)` déjà présent dans le code
était l'aveu du problème : il n'existe que pour empêcher le nombre de partir à l'infini.

Le plancher à un mois calendaire dit la seule chose vraie dans ce cas : il reste ce montant
à trouver, et il reste ce mois-ci pour le faire.

Les deux `/30.44` restants (`crowdfunding.py:187` et `551`) ont été mesurés et laissés en
place : ce sont des usages **proportionnels** — une barre de progression, et un prorata
d'intérêts courus comparé avec 90 % de tolérance. L'écart y vaut 0,077 % (365,28 contre
365 jours). La distinction est ce qui compte : le défaut n'était pas l'approximation, mais
le fait qu'elle **divise un montant affiché**.

#### FIN-08 — un piège armé qu'aucune donnée ne déclenche

Le ticket demandait de passer les montants advisory en `Decimal`. Mesure sur les données
réelles : **0 divergence sur 948 calculs** — 54 positions (valeur et montant investi) et
840 transactions, `float` contre `Decimal` arrondi au centime.

Le piège existe pourtant. Sur 200 000 montants tombant **pile sur un demi-centime**,
`round()` de Python diverge dans **50 % des cas** : il arrondit à l'entier pair, pas au
supérieur. Mais aucune donnée réelle n'atteint ce cas — les échéanciers sont stockés en
`Numeric(12,2)`, donc déjà au centime, et un produit quantité × prix ne tombe jamais pile
sur `X,XX5`. Le backtest DCA, lui, ne manipule que des montants simulés.

Verdict : réel, sans exposition. La réécriture en `Decimal` (effort M) corrigerait un
défaut que rien ne déclenche. Ce qui a réellement été trouvé en cherchant, c'est le
résidu de FIN-07 ci-dessus — un vrai bug d'affichage, à côté du ticket.

#### UX-02 — deux titres de niveau 1 par page

Huit pages portaient un `<h1>` sans être des routes : elles ne sont montées que comme
onglets. Sur `/goals`, le mot « Objectifs » apparaissait **trois fois** — fil d'Ariane,
onglet, titre — et deux `<h1>` cohabitaient dans le document.

Un lecteur d'écran suit la hiérarchie des titres pour se repérer : deux niveaux 1, ce sont
deux pages annoncées là où il n'y en a qu'une.

Les huit titres passent en `<h2>` (mêmes classes, **rendu inchangé**) et les trois
conteneurs reçoivent leur `<h1>`, masqué visuellement. Deux pages crowdfunding en avaient
deux chacune, dans leurs rendus conditionnels — le premier passage n'en avait converti
qu'un.

**Ce qui reste relève du design** : la répétition *visuelle* du même mot. Ce n'est pas un
défaut de structure et cela demande de voir les écrans.

#### UX-03 — une promesse fausse coûte plus qu'une fonctionnalité manquante

Le guide de démarrage annonçait **Crypto, Actions, ETF, Immobilier**. Trois de ces quatre
catégories n'ont aucun parcours : ni page, ni formulaire, ni type d'actif utilisé. Et il
taisait le **Crowdfunding**, qui existe pour de bon — six projets, cinquante-neuf
échéances.

Le défaut n'est pas seulement l'inexactitude : un nouvel arrivant qui cherche « Actions »
et ne trouve rien conclut que l'outil est cassé, non qu'il ne fait pas cela.

Second volet, plus discret : le guide était monté sur `/crypto`. La route d'accueil est
`/`, servie par `MasterDashboardPage`. **Il ne s'affichait donc pour personne.**

#### Les neuf derniers tickets — mesurés le 2026-09-02

**Le backlog est désormais intégralement mesuré.** Sur ces neuf, deux méritaient une
correction.

| Ticket | Mesuré | Verdict |
|---|---|---|
| **ARC-04** | deux copies du classifieur d'erreurs, **déjà divergentes** : celle des endpoints avait perdu son `logger.error` | ✅ **réel, corrigé** |
| **UX-07** | 4 sous-points : breadcrumb cliquable ✅ fait, onglet Rapports synchronisé ✅ fait, raccourci « Signaux Alpha » introuvable, **fil d'Ariane Crowdfunding figé** | 🟢 **1 sur 4, corrigé** |
| **UX-10** | le Header ne contient que menu, notifications, thème et déconnexion — ni titre courant, ni recherche | ✅ réel |
| **UX-11** | Audit Lab est une route dédiée quand le reste du Crowdfunding est en onglets | ✅ réel, mais c'est un **choix produit** |
| **ARC-13** | `^` sur react-query, axios, zod, react | ⚠️ réel, **discutable** : le lockfile fixe déjà les versions installées |
| **ARC-10** | `@nivo` dans **23 fichiers**, `lightweight-charts` dans **3** | ⚠️ **aucune librairie à retirer** — les deux servent, à des usages différents |
| **ARC-06** | `report_service` fait **697 lignes**, pas 2 744 | ⚠️ réel mais **les chiffres de l'audit sont faux** (divisé par 4 depuis) |
| **UX-06** | IntelligencePage a **4 onglets**, pas 6 | ❌ **déjà fait** — refonte de juillet |
| **ARC-08** | aucune méthode commune : `insights_service` traite frais, fiscalité et revenus passifs ; `smart_insights_service` traite santé, rééquilibrage et régime de marché | ❌ **infondé** |

**ARC-04 est le plus instructif du lot.** Le ticket signalait une fonction « dupliquée à
l'identique ». Elle ne l'était déjà plus : la copie des endpoints avait perdu son
`logger.error` final, si bien qu'une erreur générique n'y laissait **aucune trace** là où
la tâche la journalisait. L'écart portait précisément sur la capacité à diagnostiquer un
incident — c'est le défaut habituel de la duplication, invisible tant que les copies se
ressemblent.

**ARC-08 illustre l'inverse.** Deux services aux noms voisins ne sont pas deux systèmes
parallèles. Le grief réel serait le nommage — « insights » et « smart insights » ne disent
pas ce qui les sépare — pas la duplication.

#### FIN-06 à FIN-13 — mesurés le 2026-09-02

Les huit derniers tickets financiers, jamais regardés. **Un seul méritait une
correction.**

| Ticket | Mesuré | Verdict |
|---|---|---|
| **FIN-13** | `WAVES → AVES`, `WAXP → AXP`, `WEMIX → EMIX`, `WING → ING` : la règle retirait un « W » initial dès 4 caractères | ✅ **réel, corrigé** |
| **FIN-09** | l'appariement des remboursements se fait par distance de date seule, sans le montant | ✅ réel — **aucune exposition** : 59 échéances mensuelles, aucune paire à moins de 15 jours |
| **FIN-10** | `get_stock_price` rend le prix dans sa devise de cotation ; les appelants convertissent eux-mêmes | ✅ réel — **aucune exposition** : 0 action détenue |
| **FIN-07** | `int(delta / 30.44)` dans les projections d'objectifs | ✅ réel — **corrigé en deux fois** : le service le 2026-09-03, l'endpoint `/goals` le 2026-09-05. Le premier correctif avait laissé le second point d'appel. |
| **FIN-08** | montants advisory en `float` | ✅ réel mais **aucune exposition** : 0 divergence sur 948 calculs réels (54 positions × 2, 840 transactions). Le piège n'est armé que sur un demi-centime exact, où `round()` de Python arrondit à l'entier **pair** et perd un centime une fois sur deux — cas qu'aucune donnée réelle n'atteint. Les échéanciers sont en `Numeric(12,2)`, le backtest DCA est simulé. |
| **FIN-12** | le hash de déduplication ignore l'heure | ⚠️ **arbitrage documenté, pas un bug** |
| **FIN-06** | graine Monte Carlo | ❌ **déjà fait** — graine explicite, commentée |
| **FIN-11** | clamp XIRR silencieux | ❌ **déjà fait** — `logger.warning` avec le finding cité |

**FIN-13 mérite d'être raconté** : le ticket citait WIF et WLD, or **tous deux
échappaient à la règle par leur longueur** (trois caractères). Le défaut était réel, mais
pas sur les symboles annoncés — cinq autres jetons l'étaient. Corriger sur la foi du
ticket aurait traité un cas inexistant et laissé les vrais.

**FIN-12 est le cas le plus intéressant.** La docstring de `compute_transaction_hash` dit
explicitement que l'heure est exclue *pour que la même transaction réelle importée depuis
deux sources* (CSV et synchronisation) *produise le même hash*. Inclure l'heure, comme le
demande le ticket, casserait cette déduplication voulue. Un défaut voisin — la précision
des montants collapsée en `float` à 8 décimales, qui faisait collisionner deux trades PEPE
distincts — **a d'ailleurs déjà été corrigé**. Le risque résiduel (deux transactions
identiques en tout point le même jour) existe, mais l'arbitrage appartient au produit.

#### EPICs D, E, F et H — mesurés le 2026-09-01

**EPIC E (sécurité)** — les deux P1 étaient réels et sont traités :

| Ticket | Mesuré | Verdict |
|---|---|---|
| SEC-01 | vérif conditionnée à l'existence du secret : sans secret, webhook ouvert | ✅ **réel**, corrigé |
| SEC-02 | `{type(e).__name__}: {e}` renvoyé par `GET /import-status/{task_id}` | ✅ **réel**, corrigé |
| SEC-03 | `/register` renvoie « Un compte avec cet email existe déjà » | ✅ réel, **corrigé** |
| SEC-04 | 2 sous-points sur 3 déjà corrigés ; l'endpoint admin est pire que décrit | ✅ **clos** — endpoint supprimé |
| SEC-05 | fail-open décidé mais **inaudible** (WARNING) ; IDOR non exploitable ; docstring trompeuse | ✅ **corrigé** |
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
- *Fail-open* : la décision est prise et commentée, mais **le WARNING la rendait
  inaudible** — l'intégration logging de Sentry remonte les ERROR comme événements et
  laisse les WARNING à l'état de fil d'Ariane. Corrigé : 4 sites en ERROR, préfixe
  `SECURITY:` stable. **Deux de ces sites n'étaient pas au ticket** — l'échec de mise en
  blocklist au *logout*, le cas le plus trompeur : l'utilisateur voit « déconnecté » alors
  qu'un token exfiltré reste accepté, jusqu'à 7 jours pour un refresh token.

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
| UX-09 | le `<h1>` du Login porte `font-semibold` quand tout le reste — Register compris — est en serif | ✅ réel, **corrigé** |

**EPIC D (UX)** — le plus solide des quatre :

| Ticket | Mesuré | Verdict |
|---|---|---|
| UX-04 | **6 pages sur 32** gèrent un état d'erreur | ✅ réel, le plus large |
| UX-08 | 48 fichiers à spinner contre 19 à skeleton | ✅ réel |
| UX-05 | « Objectifs » → `/strategy` et « Stratégies » → `/strategies` cohabitent toujours | ✅ réel |

**Ce que la mesure de bout en bout donne** : sur **27 tickets vérifiés** (sur 50), **11
sont infondés, périmés ou déjà faits** (FIN-02 et FIN-TEST, ARC-02, ARC-09, ARC-12,
FIN-05, SEC-06, et 2 des 3 sous-points de SEC-04) et **16 sont réels** — dont plusieurs à
une sévérité bien inférieure à celle annoncée.

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

⚠️ **Correction (2026-09-01)** : ce paragraphe affirmait que « le backlog est désormais
intégralement mesuré ». C'était faux, et l'erreur est du même genre que celles que ce
document reproche à l'audit — une conclusion étendue au-delà de ce qui a été vérifié.
**31 tickets sur 50 ont été mesurés** — les EPICs A, E et G en entier, la majorité de C,
D et F ; 19 ne l'ont jamais été. Voir le tableau « État au 2026-09-01 » en tête de
document.

1. ~~NEW-13~~ — ✅ **clos le 2026-09-01**. 65 s → 2,9 s avec le cache de la tâche
   (7 actifs analysés au lieu de 1), 12 s dans le pire cas, 3,3 s pour le bandeau à
   l'écran contre 92 s au départ.
2. ~~UX-05 et ARC-11~~ — ✅ **faits le 2026-09-01**.
3. ~~VERIF-01~~ — ✅ **fait le 2026-09-01** sur 7 écrans. **À poursuivre** sur les 25
   restants : le taux de trouvailles a été de 3 défauts réels et 1 lenteur majeure pour
   7 écrans, tous invisibles aux tests.
4. **Mesurer avant d'engager** les 19 tickets jamais regardés — UX-02, UX-06 et UX-07
   d'abord, qui touchent des écrans quotidiens. 11 des 31 tickets déjà vérifiés étaient
   sans objet ; il n'y a aucune raison que le taux change sur les suivants.
5. **ARC-07 (suite)** et **ARC-03** (`transactions.py`, 1 671 lignes). `ExchangesPage`
   a désormais **5 tests de rendu** : le socle qui manquait à ARC-07 existe, son
   découpage peut reprendre. ARC-03 reste à faire précéder de tests de service.
**Les EPICs A, E et G sont clos.** Pour A, les 5 tickets étaient déjà traités ou l'ont été
en session ; pour E, SEC-01 à SEC-05 sont corrigés et SEC-06 est périmé.

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
| ✅ **UX-02** Triple titrage des onglets *(structure livrée 2026-09-03)* | ~~P1~~ | 🔴 | F-02(UX) | `IntelligencePage`, `PortfolioUnifiedPage`, `StrategyPage`, pages internes | Breadcrumb + label d'onglet + `<h1>` répètent le même mot. → Prop `embedded` sur les pages internes qui masque leur `<h1>` quand montées dans un conteneur. | ✅ **Structure corrigée** : 8 pages-onglets passent de `<h1>` à `<h2>`, 3 conteneurs reçoivent le `<h1>` qui leur manquait (masqué visuellement). Aucune n'était une route — leur titre était un titre de section. ⚠️ **Reste au design** : la répétition *visuelle* du même mot entre fil d'Ariane, onglet et titre. C'est un choix d'affichage, il demande de voir les écrans. | S |
| ✅ **UX-03** Promesses d'actifs inexistants + onboarding mal monté *(livré 2026-09-02)* | ~~P1~~ | ~~🔴/🟠~~ | F-03, F-04(UX) | `components/OnboardingWizard.tsx:35-48,93-96`, `pages/ReportsPage.tsx:354-369`, `DashboardPage.tsx:492` | Onboarding/Rapports vendent actions/ETF/immobilier/SCPI (absents) ; le wizard n'est monté que sur `/crypto`, jamais sur `/`. → Aligner sur crypto+crowdfunding ; remonter le wizard au `Layout` (ou `/`). | ✅ Les cartes annoncent Crypto, Crowdfunding, Analyses IA et Fiscalité — **le Crowdfunding, qui existe, n'était même pas mentionné**. Guide déplacé sur `/` et retiré de `/crypto`. `ReportsPage` était déjà honnête. **Clé de stockage conservée** (`user.id`) : avec `user.email`, le guide serait réapparu à ceux qui l'avaient terminé. | S |

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
| ✅ **UX-04** États d'erreur React Query *(livré 2026-09-01 — 17/17)* | ~~P1~~ | ~~🟠~~ | F-06(UX), B07 | `frontend/src/pages/*` | Échec API → écran vide/spinner infini (le RouteErrorBoundary ne capte pas les queries en erreur). → Composant `<QueryErrorState onRetry={refetch}/>` + convention « toute `useQuery` rend un état d'erreur ». | ✅ **17/17 pages à requête**, contre 6 au départ. Les 3 dernières ont demandé 3 traitements distincts (voir ci-dessous) : appliquer le même composant partout aurait dégradé 2 écrans sur 3. 13 tests de rendu, validés par canari **dans les deux sens** — retirer l'état d'erreur *et* l'étendre trop largement font échouer les tests. | M |
| ✅ **UX-05** Taxonomie Stratégie/Stratégies/Objectifs *(livré 2026-09-01)* | ~~P2~~ | ~~🟠~~ | F-05(UX) | routes + `ReportsPage` RebalancingTab | 3 emplacements, noms quasi identiques (`strategy` vs `strategies`). → « Objectifs » (`/goals`) + « Stratégies de rebalancing » (route unique) ; supprimer/relier le doublon RebalancingTab. | ✅ `/goals` sert la page, `/strategy` devient l'alias (l'inverse d'avant) ; `/strategies` vise directement `?tab=decisions` ; l'entrée de menu est renommée **« Décisions »**, d'après sa destination réelle ; breadcrumb aligné sur la convention (« Outils › Objectifs »). **RebalancingTab non touché** : moteur distinct de celui du pilier Risque (classes crypto vs MPT), sa fusion relève d'ARC-08/UX-06. | M |
| **UX-06** Consolidation onglet Intelligence | P2 | 🟠 | F-05, tableau redondance | `IntelligencePage` (6 onglets) | Insights/Smart Insights/Analyses quasi-synonymes ; Stratégies mal classée sous « Analyses IA ». → Regrouper les 3 insights ; sortir Stratégies. | ≤ 4 onglets cohérents ; labels métier explicites (« Signaux Alpha » vs « Diagnostic portefeuille »). | M |
| **UX-07** Corrections de navigation diverses | P2 | 🟡 | F-07,F-08,F-10,F-11,F-12(UX) | `MasterDashboardPage:578`, `Breadcrumb.tsx`, `CrowdfundingMesProjectsPage:36`, `ReportsPage:315` | Raccourci « Signaux Alpha » → mauvais onglet ; breadcrumb non cliquable ; breadcrumb crowdfunding figé ; onglet Rapports non synchronisé à l'URL ; dashboards jumeaux. → Lot de corrections ciblées. | Chaque sous-point vérifié individuellement (deep-link onglet, breadcrumb cliquable, cible raccourci correcte). | M |
| **UX-08** Skeletons vs spinners | P2 | 🟡 | F-09(UX) | 29 pages en `Loader2` plein écran | Saut de mise en page + perception de lenteur. → Skeletons sur les écrans à structure connue (tables, KPI rows). | Pages à structure fixe en skeleton ; pas de layout shift mesuré. | M |

---

## EPIC E — Durcissement sécurité (P1/P2)

| Ticket | Prio | Sév. | Source | Fichiers | Problème → Correctif | Critères d'acceptation | Effort |
|--------|------|------|--------|----------|----------------------|------------------------|--------|
| ✅ **SEC-01** Secret webhook Telegram obligatoire en prod *(livré 2026-09-01)* | ~~P1~~ | ~~🟠~~ | H-01 | `endpoints/telegram_webhook.py:54-57` | Vérif conditionnelle : sans secret en prod, webhook non authentifié. → Échouer au démarrage (ou 403 systématique) si `is_production and bot_enabled and not TELEGRAM_WEBHOOK_SECRET`. | En prod sans secret : le bot ne démarre pas / webhook 403 ; test de config. | S |
| ✅ **SEC-02** Ne plus fuiter les exceptions au client *(livré 2026-09-01)* | ~~P1~~ | ~~🟠~~ | H-02 | `endpoints/api_keys.py:~1404-1407,~1601-1604` | `f"...{type(e).__name__}: {e}"` renvoyé au client. → Logger l'exception complète côté serveur, message générique au client (comme `system.py`). | Aucune réponse client ne contient de détail d'exception ; logs serveur conservent le détail. | XS |
| ✅ **SEC-03** Énumération de comptes au register *(livré 2026-09-01)* | ~~P2~~ | ~~🔵~~ | M-01 | `endpoints/auth.py:145-149` | Confirme l'existence d'un email. → Message générique / 201 neutre, comme forgot/resend. | `/register` ne distingue plus email existant vs nouveau. **Sévérité abaissée 🟡→🔵** : 1 seul utilisateur en base, l'oracle ne révèle que l'adresse du propriétaire. À faire pour la cohérence avec forgot/resend, qui sont déjà neutres. | XS |
| ✅ **SEC-04** Durcissements config *(clos 2026-09-01)* | ~~P2~~ | ~~🟡~~ | M-03,M-04,M-05 | `main.py` (admin_fix_mirrors), `core/rate_limit.py:10-19`, `core/config.py:125-127` | Dump debug admin verbeux ; `X-Forwarded-For` spoofable ; Redis TLS `CERT_NONE`. → Réduire le log admin (compteurs) ; ne lire XFF que derrière proxy de confiance (hop Render) ; Redis `CERT_REQUIRED` + CA Upstash. | ✅ XFF non spoofable (lecture depuis la droite) et ✅ Redis en TLS vérifié **étaient déjà faits**. **Reste** : `admin_fix_mirrors` (232 l.) exécute un `ALTER TABLE` depuis HTTP et renvoie un dump des transactions — c'est le chemin des fantômes Tangem. **→ supprimé** (232 lignes). | S |
| ✅ **SEC-05** Documenter/renforcer fingerprint & fail-open *(livré 2026-09-01)* | ~~P3~~ | ~~🔵~~ | M-02,L-01,L-03,L-04 | `core/security.py:15-21`, `api_keys.py:~1678`, `api/deps.py:155-176`, blocklist Redis | Fingerprint UA-only (faux sentiment de sécurité) ; task_id sans ownership ; fail-open silencieux ; blocklist fail-open si Redis down. → Documenter explicitement les limites ; ajouter `user_id` aux tâches d'import ; stratégie fail-open/closed décidée + alerte Redis. | ✅ Le fail-open **n'est plus silencieux** : décidé, commenté, loggué en WARNING (`deps.py:115`, `auth.py:517`). ✅ Les 4 sites passent en **ERROR** avec préfixe `SECURITY:` — c'est ce niveau que Sentry remonte en alerte, un WARNING ne laissant qu'un fil d'Ariane. ✅ Ownership vérifié sur `import-status` (même 404 qu'une tâche absente). ✅ Docstring du fingerprint réécrite. | S |
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
| ✅ **ARC-11** Centraliser le formatage monétaire *(livré 2026-09-01)* | ~~🟡~~ | C05 | **4 fichiers** formataient une devise à la main — l'audit en annonçait 43, ma propre mesure 13 : les deux comptaient les fichiers utilisant correctement `formatCurrency` | Formatage dispersé → incohérences devise/décimales. → Tout passer par `lib/utils.formatCurrency`. | ✅ `CalendarPage` (5×), `StrategiesSection` (3×), les deux formulaires de transaction. `formatCurrency` accepte désormais `maximumFractionDigits`, pour que les affichages volontairement arrondis n'aient plus de raison de se recréer un formateur local. Garde-fou statique sur tout `src/`. | M |

---

## EPIC G — Accessibilité (P2)

| Ticket | Sév. | Source | Problème → Correctif | Critères d'acceptation | Effort |
|--------|------|--------|----------------------|------------------------|--------|
| ✅ **A11Y-01** `aria-label` sur tous les boutons icône *(livré 2026-09-01)* | ~~🟠~~ | A-01 | **32** boutons `size="icon"` mesurés (l'audit en annonçait 29), **9 sans nom accessible** : le lecteur d'écran annonçait « bouton », rien d'autre. | ✅ 0 restant, vérifié par un test qui balaie tout `src/`. Les boutons de pagination gagnent `aria-current`. | M |
| ✅ **A11Y-02** `prefers-reduced-motion` sur framer-motion *(livré 2026-09-01)* | ~~🟠~~ | A-02, F-15 | **L'audit vise à côté** : Login n'anime rien en JS, et `number-ticker`/`empty-state` avaient déjà leur garde `matchMedia`. Restaient `animated-number` et les **40 `motion.*`** du dashboard patrimoine. | ✅ `MotionConfig reducedMotion="user"` à la racine : couvre l'existant **et tout composant futur**. La media query CSS ne les atteignait pas — framer-motion pilote ses valeurs en JS, il n'y a aucune animation CSS à neutraliser. | S |
| ✅ **A11Y-03** Cibles tactiles & labels rail *(livré 2026-09-01)* | ~~🟡~~ | A-04, A-03, F-16 | Libellés du rail révélés au survol seul → **invisibles pendant toute la tabulation**. 13 boutons de 24 à 32 px. | ✅ `group-focus-within` ajouté. Cible tactile portée à 44 px **par pseudo-élément, sans changer le rendu** : le problème n'est pas la taille apparente mais la zone qui répond au doigt, et agrandir les boutons casserait la densité des tableaux. | S |
| ✅ **A11Y-04** Contrastes secondaires *(livré 2026-09-01)* | ~~🔵~~ | A-05 | **Chiffré** par conversion OKLCH → sRGB, au lieu de « possiblement » : `--gain` clair **3,85:1** · `muted-foreground/70` **3,07:1** · `muted-foreground/80` **3,76:1** (4 occurrences que la mesure initiale avait manquées — c'est le test qui les a trouvées). Le reste passait, thème sombre inclus (gain 8,48:1). | ✅ `--gain` abaissé de L 0.58 à **0.53** (4,68:1), opacités retirées. Le test recalcule le contraste **depuis `index.css`** : il vaudra pour tout token ajouté plus tard. | S |

---

## EPIC H — Polish & faible sévérité (P3)

| Ticket | Source | Correctif | Effort |
|--------|--------|-----------|--------|
| ❌ **FIN-05** Corriger la docstring de signe `_xirr` *(déjà correct — vérifié 2026-09-01)* | F-08 | Refléter la convention réelle (négatif = sortie). | XS |
| ❌ **FIN-06** Découpler les tirages Monte Carlo *(déjà fait — mesuré 2026-09-02)* | F-09 | Graine explicite et documentée : `seed` forcé pour les tests, horloge XOR user_id en production. | S |
| ✅ **FIN-07** Mois restants via `relativedelta` *(livré 2026-09-03, complété 2026-09-05)* | F-10 | L'approximation se trompait d'un mois dans **3 % des échéances** (118 cas sur 3 621). Rare mais jamais anodin : ce nombre divise le montant restant, donc un mois de moins demande un effort mensuel plus élevé — jusqu'à **+50 %** sur une échéance courte. **Second point d'appel corrigé le 2026-09-05** : `endpoints/goals.py` calculait encore `jours / 30,44` pour le même chiffre affiché. Les deux écrans divergeaient sur **99,5 % des échéances** ; à un jour du terme, 0,03 mois transformait 10 000 € restants en « 304 400 €/mois nécessaire ». | XS |
| ❌ **FIN-08** `Decimal` pour montants advisory affichés *(écarté après mesure 2026-09-05)* | F-11 | **0 divergence sur 948 calculs réels.** Le piège ne s'arme que sur un demi-centime exact, que ni les échéanciers (`Numeric(12,2)`) ni les produits quantité × prix n'atteignent. | M |
| ✅ **FIN-09** Appariement remboursement par date+montant *(livré 2026-09-03)* | F-12 | Le montant devient le premier critère quand il est connu ; sinon la date, comme avant. Tolérance de 1 % pour l'arrondi de la dernière échéance et les frais de virement. Aucune exposition actuelle (59 échéances, aucune paire à moins de 15 jours) mais le piège s'arme dès qu'un projet a des versements rapprochés. | S |
| **FIN-10** Centraliser conversion prix actions | F-13 | `price_service.get_price` renvoie toujours en devise demandée. | S |
| ❌ **FIN-11** Logguer le clamp XIRR *(déjà fait — mesuré 2026-09-02)* | F-14 | Le `logger.warning` est en place, avec le finding F-14 cité en commentaire. | XS |
| **FIN-12** Hash dédup avec heure | F-15 | Inclure l'heure / `external_id` pour ne pas fusionner 2 DCA identiques le même jour. | S |
| ✅ **FIN-13** Earn/wrapped par table explicite *(livré 2026-09-02)* | F-16 | Remplacer le strip de préfixe `W` par une table de variantes connues. **WIF/WLD n'étaient pas concernés** (3 caractères) ; les jetons réellement mutilés étaient WAVES, WAXP, WEMIX, WING, WHITE. | S |
| ❌ **ARC-12** Supprimer l'alias mort `fetchUser` *(infondé : utilisé par `VerifyEmailPage` — 2026-09-01)* | D02 | `authStore.ts` — retirer l'alias inutilisé. | XS |
| **ARC-13** Épingler les deps critiques | C02 | Pin strict react-query/axios/zod (au-delà du lockfile). | XS |
| ✅ **UX-09** `font-serif` sur h1 du Login *(livré 2026-09-03)* | F-13(UX) | Le Login était le **seul** titre de l'application hors serif — sa page jumelle Register l'était déjà au même endroit. Corrigé, **et la page annonçait « Actions »** dans ses pastilles comme dans son accroche : même promesse sans parcours qu'UX-03, sur le premier écran vu. | XS |
| ⚠️ **UX-10** Remplir le Header *(mesuré 2026-09-03)* | F-14(UX) | **Le cmd-K n'est PAS présent** : `cmdk` est installé mais ne sert qu'au sélecteur de plateforme, et aucun raccourci global n'existe. Une palette de recherche est un chantier entier (que cherche-t-on ? actifs, transactions, projets, pages ?), pas un ticket S. Quant au titre courant, l'ajouter créerait un **quatrième** titrage juste après la correction d'UX-02. **Demande un arbitrage produit, et de voir les écrans.** | S |
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
