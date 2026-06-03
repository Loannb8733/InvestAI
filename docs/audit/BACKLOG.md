# InvestAI — Backlog priorisé d'après l'audit du 2026-06-03

> Source : 4 rapports d'audit (`01-calculs-financiers.md`, `02-architecture-code.md`, `03-fonctionnalites-ux.md`, `04-securite-donnees.md`).
> Couvre **45 findings**. Chaque ticket renvoie à son/ses ID(s) d'origine.

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
| **1 — Exactitude** | EPIC A (FIN-01→04) + FIN-TEST + UX-01 | Le risque dominant : des montants faux de ~8-9 % pour la majorité des traders crypto. Plus le 404 du menu (1 ligne). Rien d'autre ne doit passer devant. |
| **2 — Robustesse & vérité produit** | EPIC C (async, ORM, erreurs) + EPIC B (onboarding, promesses, titrage) + EPIC E P1 (sécurité élevée) | Stabilise le backend (bugs prod non-déterministes) et arrête de promettre des features absentes. |
| **3 — Cohérence UX & sécurité moyenne** | EPIC D + EPIC E P2 + EPIC G (a11y) | États d'erreur, taxonomie, durcissements. |
| **4 — Dette & polish** | EPIC F (god-files) + EPIC H (P3) | Refactors à dérouler en continu, sans bloquer la valeur. |

> **VERIF-01** (rendu design) est à faire dès la vague 1 ou 2 : sans elle, on ne sait pas si le chantier design existe.

---

## EPIC A — Exactitude financière (P0)

> Racine commune des deux premiers tickets : `Transaction.currency` est faux ou ignoré. À traiter ensemble pour garantir la parité dashboard ↔ XIRR ↔ rapports.

| Ticket | Sév. | Source | Fichiers | Problème → Correctif | Critères d'acceptation | Effort |
|--------|------|--------|----------|----------------------|------------------------|--------|
| **FIN-01** Devise réelle des trades exchange | 🔴 | F-01 | `tasks/sync_exchanges.py` (~257,282,338,394,452,521,585,639,809,861), `services/exchanges/*` | Toutes les `Transaction` de la sync sont `currency="EUR"` en dur alors que le `price` vient de paires USD/USDT. → Détecter la quote currency de chaque paire ; stocker `currency` réelle + `conversion_rate` = taux EUR/USD à la **date d'exécution** (le moteur FIFO sait exploiter `fx_rate`). Script de migration pour re-traiter l'historique. | Un achat `BTCUSDT` produit un coût de base en EUR exact (±0,1 %) ; `avg_buy_price` homogène ; test FIN-TEST #1 vert ; script de backfill idempotent validé sur données synthétiques. | L |
| **FIN-02** Refonte XIRR (devise + flux) | 🔴 | F-02, F-03, F-04 | `services/analytics_service.py:1564-1644` | (a) ignore `tx.currency` (suppose tout USD) ; (b) compte `TRANSFER_IN/OUT` comme cash-flows fantômes ; (c) ignore `DIVIDEND`/`INTEREST`. → Lire `tx.currency` ligne à ligne (même pipeline que `metrics_service`) ; exclure les transferts internes ; ajouter dividendes+intérêts comme flux entrants. | XIRR de référence correct sur cash-flows connus (FIN-TEST #2) ; transferts internes appariés n'affectent pas le XIRR (#3) ; div/intérêts comptés (#4) ; parité P&L/rendement dashboard↔XIRR < 0,5 %. | M |
| **FIN-03** Coût de base des transferts non appariés | 🟠→P0 | F-06 | `services/metrics_service.py:155-161,720-758`, `transfer_service.py:114-148` | Un `TRANSFER_IN` sans transit apparié crée une couche à **coût zéro** → P&L latent massivement surévalué. Règle divergente entre CUMP et FIFO. → À défaut d'appariement, utiliser `source_asset.avg_buy_price` ; unifier la règle entre les deux moteurs. | Un transfer_in non apparié n'apparaît jamais à coût zéro ; CUMP et FIFO donnent le même P&L (test dédié) ; couverture du cas « sync partielle ». | M |
| **FIN-04** Service de taux de change robuste | 🟠 | F-05, A02 | `services/price_service.py:218-238`, `services/metrics_service.py:388-391,402,1325,1524` | Taux de repli figés en dur (`0.92`/`1.09`) + `except: pass` qui avalent les échecs forex → valorisation silencieusement fausse. → Un seul service de taux : dernière valeur connue **persistée** (pas une constante), TTL court, flag `forex_stale` propagé jusqu'à l'UI ; remplacer les 3 swallow par log + flag `partial`. | Aucun taux en dur dans le code ; `forex_stale` exposé dans la réponse API et affiché ; les échecs forex sont loggés (plus de `pass`) ; test FIN-TEST #7. | M |
| **FIN-TEST** Tests numériques de référence | 🔴 | §3 rapport 01 | `backend/tests/unit/` | Les tests « parity/xirr » actuels ne vérifient **aucune valeur numérique** (XIRR juste borné `[-95,1000]`, parité tolérée à 1 %). → Ajouter des tests unitaires purs avec valeurs attendues : coût de base multi-devises, XIRR golden (10 000€→11 000€/1 an = 10 %), exclusion transferts, div/intérêts, transfer zéro-coût, forex périmé. | ≥ 7 nouveaux tests unitaires déterministes (sans Docker/HTTP) ; tournent en CI ; chacun mappé à un finding FIN-xx ; parité resserrée à < 0,5 %. | M |

---

## EPIC B — Navigation & vérité produit (P0/P1)

| Ticket | Prio | Sév. | Source | Fichiers | Problème → Correctif | Critères d'acceptation | Effort |
|--------|------|------|--------|----------|----------------------|------------------------|--------|
| **UX-01** Menu « Stratégies » → 404 | P0 | 🔴 | F-01(UX) | `components/layout/NavRail.tsx:67`, `App.tsx` | `/strategies` n'a ni route ni redirect → 404. → Ajouter `<Route path="strategies" element={<Navigate to="/intelligence?tab=strategies" replace/>}/>` (ou pointer le menu directement). | Clic « Stratégies » n'atteint jamais la 404 ; test e2e de navigation menu. | XS |
| **UX-02** Triple titrage des onglets | P1 | 🔴 | F-02(UX) | `IntelligencePage`, `PortfolioUnifiedPage`, `StrategyPage`, pages internes | Breadcrumb + label d'onglet + `<h1>` répètent le même mot. → Prop `embedded` sur les pages internes qui masque leur `<h1>` quand montées dans un conteneur. | Aucune page d'onglet n'affiche un titre dupliqué ; le titre unique vit dans le conteneur. | S |
| **UX-03** Promesses d'actifs inexistants + onboarding mal monté | P1 | 🔴/🟠 | F-03, F-04(UX) | `components/OnboardingWizard.tsx:35-48,93-96`, `pages/ReportsPage.tsx:354-369`, `DashboardPage.tsx:492` | Onboarding/Rapports vendent actions/ETF/immobilier/SCPI (absents) ; le wizard n'est monté que sur `/crypto`, jamais sur `/`. → Aligner sur crypto+crowdfunding ; remonter le wizard au `Layout` (ou `/`). | Plus aucune mention d'actif non géré ; un nouveau compte voit l'onboarding dès `/`. | S |

---

## EPIC C — Robustesse backend (P1)

| Ticket | Sév. | Source | Fichiers | Problème → Correctif | Critères d'acceptation | Effort |
|--------|------|--------|----------|----------------------|------------------------|--------|
| **ARC-01** Boucle async / engine Celery | 🔴 | A01, C06 | `core/database.py:14`, `tasks/*` (7 fichiers `new_event_loop`) | Engine async créé une fois au niveau module, réutilisé par des boucles recréées à chaque tâche → « Future attached to a different loop », fuites de pool. → Un seul helper `run_async` dans `tasks/__init__.py` + engine worker en `NullPool` (ou `asyncio.run` partout). | 1 seul helper async ; 0 `new_event_loop` dupliqué ; test de charge Celery local sans erreur de boucle. | M |
| **ARC-02** Relations ORM + eager loading | 🟠 | B03 | tous les `models/*.py`, endpoints lourds | `relationship()` = 0 partout ; jointures FK manuelles ; aucun `selectinload` → N+1. → Déclarer les relations clés (portfolio→assets→transactions) avec `lazy="selectin"`. | Relations déclarées sur les 5 modèles centraux ; dashboard/portfolio sans N+1 (compteur de requêtes en test) ; pas de régression de valeur. | L |
| **ARC-03** Sortir la logique des god-endpoints | 🟠 | B02 | `endpoints/transactions.py` (70 req.), `dashboard.py` (37), `api_keys.py` (59) | Logique métier + SQL dans les endpoints → non réutilisable par Celery, non testable hors HTTP. → Extraire `transaction_service.py`, `api_key_service.py` ; l'endpoint = validation + appel service + mapping. | Endpoints réduits au routing ; logique couverte par tests de service ; réutilisée par au moins une tâche. | L |
| **ARC-04** Factoriser `_classify_and_mark_error` | 🟠 | B04 | `tasks/sync_exchanges.py:39`, `endpoints/api_keys.py:27` | Fonction dupliquée à l'identique. → `services/exchange_error_classifier.py` importé des deux côtés. | 1 seule implémentation ; les deux appelants l'importent ; test unitaire de classification. | XS |

---

## EPIC D — États d'erreur & cohérence UX (P1/P2)

| Ticket | Prio | Sév. | Source | Fichiers | Problème → Correctif | Critères d'acceptation | Effort |
|--------|------|------|--------|----------|----------------------|------------------------|--------|
| **UX-04** États d'erreur React Query | P1 | 🟠 | F-06(UX), B07 | `frontend/src/pages/*` (26/36 sans gestion) | Échec API → écran vide/spinner infini (le RouteErrorBoundary ne capte pas les queries en erreur). → Composant `<QueryErrorState onRetry={refetch}/>` + convention « toute `useQuery` rend un état d'erreur ». | Composant créé ; branché sur ≥ pages critiques (dashboard, portfolio, transactions, exchanges, intelligence) ; test simulant un 500. | M |
| **UX-05** Taxonomie Stratégie/Stratégies/Objectifs | P2 | 🟠 | F-05(UX) | routes + `ReportsPage` RebalancingTab | 3 emplacements, noms quasi identiques (`strategy` vs `strategies`). → « Objectifs » (`/goals`) + « Stratégies de rebalancing » (route unique) ; supprimer/relier le doublon RebalancingTab. | Un seul emplacement par concept ; URLs sans collision singulier/pluriel. | M |
| **UX-06** Consolidation onglet Intelligence | P2 | 🟠 | F-05, tableau redondance | `IntelligencePage` (6 onglets) | Insights/Smart Insights/Analyses quasi-synonymes ; Stratégies mal classée sous « Analyses IA ». → Regrouper les 3 insights ; sortir Stratégies. | ≤ 4 onglets cohérents ; labels métier explicites (« Signaux Alpha » vs « Diagnostic portefeuille »). | M |
| **UX-07** Corrections de navigation diverses | P2 | 🟡 | F-07,F-08,F-10,F-11,F-12(UX) | `MasterDashboardPage:578`, `Breadcrumb.tsx`, `CrowdfundingMesProjectsPage:36`, `ReportsPage:315` | Raccourci « Signaux Alpha » → mauvais onglet ; breadcrumb non cliquable ; breadcrumb crowdfunding figé ; onglet Rapports non synchronisé à l'URL ; dashboards jumeaux. → Lot de corrections ciblées. | Chaque sous-point vérifié individuellement (deep-link onglet, breadcrumb cliquable, cible raccourci correcte). | M |
| **UX-08** Skeletons vs spinners | P2 | 🟡 | F-09(UX) | 29 pages en `Loader2` plein écran | Saut de mise en page + perception de lenteur. → Skeletons sur les écrans à structure connue (tables, KPI rows). | Pages à structure fixe en skeleton ; pas de layout shift mesuré. | M |

---

## EPIC E — Durcissement sécurité (P1/P2)

| Ticket | Prio | Sév. | Source | Fichiers | Problème → Correctif | Critères d'acceptation | Effort |
|--------|------|------|--------|----------|----------------------|------------------------|--------|
| **SEC-01** Secret webhook Telegram obligatoire en prod | P1 | 🟠 | H-01 | `endpoints/telegram_webhook.py:54-57` | Vérif conditionnelle : sans secret en prod, webhook non authentifié. → Échouer au démarrage (ou 403 systématique) si `is_production and bot_enabled and not TELEGRAM_WEBHOOK_SECRET`. | En prod sans secret : le bot ne démarre pas / webhook 403 ; test de config. | S |
| **SEC-02** Ne plus fuiter les exceptions au client | P1 | 🟠 | H-02 | `endpoints/api_keys.py:~1404-1407,~1601-1604` | `f"...{type(e).__name__}: {e}"` renvoyé au client. → Logger l'exception complète côté serveur, message générique au client (comme `system.py`). | Aucune réponse client ne contient de détail d'exception ; logs serveur conservent le détail. | XS |
| **SEC-03** Énumération de comptes au register | P2 | 🟡 | M-01 | `endpoints/auth.py:145-149` | Confirme l'existence d'un email. → Message générique / 201 neutre, comme forgot/resend. | `/register` ne distingue plus email existant vs nouveau dans la réponse. | S |
| **SEC-04** Durcissements config | P2 | 🟡 | M-03,M-04,M-05 | `main.py` (admin_fix_mirrors), `core/rate_limit.py:10-19`, `core/config.py:125-127` | Dump debug admin verbeux ; `X-Forwarded-For` spoofable ; Redis TLS `CERT_NONE`. → Réduire le log admin (compteurs) ; ne lire XFF que derrière proxy de confiance (hop Render) ; Redis `CERT_REQUIRED` + CA Upstash. | Rate limiting non contournable par header ; Redis en TLS vérifié ; endpoints admin one-shot retirés ou minimisés. | M |
| **SEC-05** Documenter/renforcer fingerprint & fail-open | P3 | 🟡/🔵 | M-02,L-01,L-03,L-04 | `core/security.py:15-21`, `api_keys.py:~1678`, `api/deps.py:155-176`, blocklist Redis | Fingerprint UA-only (faux sentiment de sécurité) ; task_id sans ownership ; fail-open silencieux ; blocklist fail-open si Redis down. → Documenter explicitement les limites ; ajouter `user_id` aux tâches d'import ; stratégie fail-open/closed décidée + alerte Redis. | Décisions documentées ; ownership vérifié sur import-status ; alerte si Redis indisponible. | M |
| **SEC-06** Migration `python-jose` → `pyjwt` (veille) | P3 | 🔵 | §3 rapport 04 | `requirements.txt` | `python-jose` peu maintenue ; `bcrypt==4.0.1` ancien. → Évaluer migration `pyjwt`, surveiller bcrypt. | Décision tranchée (migrer ou accepter le risque, daté). | S |

---

## EPIC F — Dette structurelle / god-files (P2)

| Ticket | Sév. | Source | Fichiers | Problème → Correctif | Critères d'acceptation | Effort |
|--------|------|--------|----------|----------------------|------------------------|--------|
| **ARC-05** Découper `prediction_service.py` | 🟠 | B01 | `services/prediction_service.py` (3 733 LOC) | God-file : prédiction + régime + sentiment + anomalies + cache + accuracy. → Découper en `forecasting/`, `regime/`, `sentiment/`, `accuracy/` (la couche `ml/` existe déjà). | Aucun fichier > ~800 LOC sur ce périmètre ; chaque sous-domaine testable isolément ; pas de régression. | L |
| **ARC-06** Découper les god-services secondaires | 🟡 | C04 | `report_service.py` (2744), `metrics_service.py` (2127), `analytics_service.py` (2111) | Mêmes risques à moindre échelle. → Découpage progressif calcul/agrégation/formatage. | Réduction mesurable de la taille ; tests conservés verts. | L |
| **ARC-07** Découper `ExchangesPage.tsx` | 🟠 | B06 | `pages/ExchangesPage.tsx` (2185) | Monolithe (dialogs, formulaires, tables, sync, cold wallets). → `ApiKeyForm`, `ApiKeyList`, `SyncStatusCard`, `ColdWalletSection` + hooks. | Page < ~400 LOC ; sous-composants réutilisables ; re-renders réduits. | L |
| **ARC-08** Trancher le doublon insights | 🟠 | B05 | `services/insights_service.py` (403) vs `smart_insights_service.py` (1525) + endpoints | Deux systèmes parallèles, recouvrement probable. → Confirmer le vivant, déprécier/supprimer l'ancien. | Une seule source de vérité insights ; code mort supprimé. | M |
| **ARC-09** Unifier les `queryKey` | 🟡 | C03 | ~14 clés hardcodées (`charts/*`, `PlatformSelect`, `DashboardMunitionsCard`) | Contournent `lib/queryKeys.ts` → invalidation incohérente, caches périmés. → Migrer toutes les clés vers la factory. | 0 `queryKey` hardcodé ; invalidation testée. | S |
| **ARC-10** Stratégie librairies de charts | 🟡 | C01 | `frontend/package.json:17-21,45` | `@nivo/*` **et** `lightweight-charts`. → Choisir par cas d'usage et documenter, ou consolider ; retirer la lib non utilisée. | Décision documentée ; bundle allégé si retrait. | S |
| **ARC-11** Centraliser le formatage monétaire | 🟡 | C05 | 43 fichiers avec `toLocaleString`/`Intl`/`formatCurrency` | Formatage dispersé → incohérences devise/décimales. → Tout passer par `lib/utils.formatCurrency`. | 1 seul point de formatage ; cohérence visuelle vérifiée. | M |

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
| **FIN-05** Corriger la docstring de signe `_xirr` | F-08 | Refléter la convention réelle (négatif = sortie). | XS |
| **FIN-06** Découpler les tirages Monte Carlo | F-09 | Graines distinctes ou re-tirage proba/ETA ; afficher un intervalle. | S |
| **FIN-07** Mois restants via `relativedelta` | F-10 | Remplacer `delta/30.44` par mois calendaires exacts. | XS |
| **FIN-08** `Decimal` pour montants advisory affichés | F-11 | Cashflows stress test / DCA affichés au centime en `Decimal`. | M |
| **FIN-09** Appariement remboursement par date+montant | F-12 | Pondérer la réconciliation ; documenter l'arrondi « last installment ». | S |
| **FIN-10** Centraliser conversion prix actions | F-13 | `price_service.get_price` renvoie toujours en devise demandée. | S |
| **FIN-11** Logguer le clamp XIRR | F-14 | Alerter quand `[-95,1000]` s'active au lieu de borner en silence. | XS |
| **FIN-12** Hash dédup avec heure | F-15 | Inclure l'heure / `external_id` pour ne pas fusionner 2 DCA identiques le même jour. | S |
| **FIN-13** Earn/wrapped par table explicite | F-16 | Remplacer le strip de préfixe `W` par une table de variantes connues (évite WIF/WLD cassés). | S |
| **ARC-12** Supprimer l'alias mort `fetchUser` | D02 | `authStore.ts` — retirer l'alias inutilisé. | XS |
| **ARC-13** Épingler les deps critiques | C02 | Pin strict react-query/axios/zod (au-delà du lockfile). | XS |
| **UX-09** `font-serif` sur h1 du Login | F-13(UX) | Cohérence de marque dès l'entrée. | XS |
| **UX-10** Remplir le Header | F-14(UX) | Breadcrumb/titre courant + recherche globale (cmd-K déjà présent). | S |
| **UX-11** Crowdfunding Audit Lab : onglet ou route | F-17(UX) | Trancher l'asymétrie onglets vs route dédiée. | S |

---

## VÉRIFICATION (transverse)

| Ticket | Prio | Problème → Action | Critères d'acceptation | Effort |
|--------|------|-------------------|------------------------|--------|
| **VERIF-01** Audit design **rendu** (pas le code) | P1 | Le 8,5/10 design est non vérifié (lu dans le CSS, pas regardé). → Rendre l'app en local (build + Claude_Preview), capturer chaque écran clé en dark **et** light, à 375/768/1024/1440 px, et juger visuellement : hiérarchie, hardiesse réelle, cohérence, identité vs template. | Captures de tous les écrans clés ; verdict design **fondé sur le rendu** ; findings visuels ajoutés au backlog. | M |
| **VERIF-02** Quantifier l'impact FIN-01/02 | P1 | Mesurer l'erreur réelle de coût de base / P&L sur un échantillon **anonymisé/synthétique** (jamais la DB prod). | Rapport chiffré de l'écart avant/après FIN-01/02. | S |

---

## « Definition of Done » par domaine (cible réaliste, pas un chiffre rond)

- **Calculs financiers** : EPIC A + FIN-TEST livrés ; parité dashboard↔XIRR↔rapports < 0,5 % ; tous montants en `Decimal` sur les chemins affichés ; aucun taux en dur ; `forex_stale` visible. → *score défendable seulement une fois les tests de référence verts.*
- **Architecture & code** : ARC-01→04 livrés ; aucun fichier > ~800 LOC sur les god-files traités ; relations ORM sur les modèles centraux ; 0 `except: pass` sur du calcul financier.
- **Fonctionnalités & UX** : EPIC B + UX-04 livrés ; 0 lien mort ; états d'erreur sur toutes les pages critiques ; promesses produit alignées sur le périmètre réel ; **VERIF-01 effectué**.
- **Sécurité** : 0 finding 🟠 ouvert (SEC-01/02) ; durcissements SEC-04 ; **+ processus continu** : veille CVE (npm/pip audit en CI), rotation de clés, alerte Redis. La sécurité n'est jamais « finie ».
