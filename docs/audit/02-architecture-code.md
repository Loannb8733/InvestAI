# Audit InvestAI — Architecture & Qualité de code

> Périmètre : ~51 500 LOC backend (FastAPI/SQLAlchemy/Celery), ~36 000 LOC frontend (Vite/React 18/TS).
> Analyse statique, lecture seule. Date : 2026-06-03.

---

## Résumé exécutif

**Note de santé du code : 6.5 / 10**

Le projet est globalement plus sain que la moyenne d'une fintech à ce stade : sécurité de la config soignée (secrets sans défaut, COOKIE_SECURE auto, store Zustand qui ne persiste pas les tokens), typage TS quasi-irréprochable (4 `any` seulement, tous légitimes), couverture de tests réelle et orientée domaine financier (44 fichiers de tests backend dont xirr, monte-carlo, stress, parités). Ce qui plombe la note, c'est la **dette structurelle accumulée** : god-files massifs, couche de données entièrement manuelle (zéro relation ORM), et une gestion d'erreurs trop permissive (352 `except Exception`, dont plusieurs avalent silencieusement des erreurs dans le calcul financier).

### Top 3 problèmes structurels

1. **God-files hors de contrôle.** `prediction_service.py` (3 733 LOC), `report_service.py` (2 744), `metrics_service.py` (2 127), `analytics_service.py` (2 111) côté services ; `api_keys.py` (1 692) et `dashboard.py` (1 340) côté endpoints ; `ExchangesPage.tsx` (2 185) et `api.ts` (1 431) côté front. Maintenabilité et testabilité sévèrement dégradées.
2. **Couche de données 100 % manuelle — aucune relation ORM.** `grep relationship() → 0` sur tous les modèles. Tout passe par des `select()` + jointures FK à la main, dont **70 requêtes directes dans `transactions.py`** et 37 dans `dashboard.py` (logique métier dans la couche endpoint). Pas un seul `selectinload`/`joinedload` → eager loading impossible, surface N+1 large.
3. **Gestion d'erreurs trop large + duplication async.** 352 `except Exception`, 47 blocs `except … : pass` (dont 3 dans `metrics_service.py` sur des taux de change → valeurs financières silencieusement faussées). 7 helpers `run_async`/`new_event_loop` copiés-collés dans `app/tasks/` réutilisant l'engine async global défini au niveau module → risque "Future attached to a different loop" avec asyncpg.

---

## Findings par sévérité

### 🔴 Critique

| ID | Sév | Fichier:ligne | Problème | Risque | Reco |
|----|-----|---------------|----------|--------|------|
| A01 | 🔴 | `app/core/database.py:14` + `app/tasks/*` (7 fichiers, `new_event_loop`) | Engine async SQLAlchemy/asyncpg créé une seule fois au niveau module, puis réutilisé par chaque tâche Celery via un `asyncio.new_event_loop()` recréé à chaque appel (`price_updates.py:70`, `predictions.py:18`, `emails.py:14`, `snapshots.py:23`, `cleanup.py:14`, `monitor_delays.py:13`, `history_cache.py:42`). Les connexions asyncpg poolées sont liées à la boucle qui les a créées. | Erreurs intermittentes "got Future attached to a different loop", connexions corrompues, fuites de pool sous charge Celery. Bugs non-déterministes en prod. | Soit `asyncio.run()` partout (crée/détruit la boucle proprement) + `NullPool` pour l'engine côté worker, soit un engine dédié worker recréé par boucle. Centraliser **un seul** helper `run_async` dans `app/tasks/__init__.py`. |
| A02 | 🔴 | `app/services/metrics_service.py:402,1325,1524` | `except Exception: pass` autour de `get_forex_rate` / récupération de prix dans le calcul de valorisation du portefeuille. | Un taux de change qui échoue est silencieusement ignoré → la valeur du portefeuille affichée à l'utilisateur est fausse sans aucun signal. Sur une fintech, c'est un bug de correction de données. | Logger en `warning` minimum, exposer un flag `stale`/`partial` dans la réponse API, et utiliser un fallback explicite documenté (dernier taux connu) plutôt qu'un silence. |

### 🟠 Majeur

| ID | Sév | Fichier:ligne | Problème | Risque | Reco |
|----|-----|---------------|----------|--------|------|
| B01 | 🟠 | `app/services/prediction_service.py` (3 733 LOC) | God-file : prédiction prix + détection régime + sentiment + anomalies + cache + accuracy dans une seule classe. | Impossible à tester unitairement par responsabilité, fusions git conflictuelles, charge cognitive énorme. | Découper par domaine : `forecasting/`, `regime/`, `sentiment/`, `accuracy/`. La couche `ml/` existe déjà — y déplacer la logique pure. |
| B02 | 🟠 | `app/api/v1/endpoints/transactions.py` (70 `db.execute`/`select`) ; `dashboard.py` (37) ; `api_keys.py` (59) | Logique métier + requêtes SQL directement dans les endpoints (god-endpoints). `api_keys.py` mélange routing HTTP + chiffrement Fernet + classification d'erreurs exchange. | Violation de la séparation endpoint→service→model. Logique non réutilisable par Celery, non testable hors HTTP, duplication. | Extraire la logique dans `services/transaction_service.py` (n'existe pas), `services/api_key_service.py`. L'endpoint ne doit faire que validation + appel service + mapping réponse. |
| B03 | 🟠 | Tous les modèles (`app/models/*.py`) — `relationship()` = 0 | Aucune relation ORM déclarée (`Portfolio` n'a ni `assets` ni `transactions`). Tout est jointure FK manuelle. | Pas d'eager loading possible → N+1 latents, code de jointure dupliqué partout, intégrité référentielle gérée à la main. | Déclarer les `relationship()` + `lazy="selectin"` sur les accès en lot (portfolio→assets→transactions). Gros gain perf dashboard. |
| B04 | 🟠 | `app/tasks/sync_exchanges.py:39` ↔ `app/api/v1/endpoints/api_keys.py:27` | Fonction `_classify_and_mark_error` dupliquée à l'identique (classification 401/403/429/JSON Kraken). | Divergence garantie à terme : un fix dans l'une oublie l'autre → comportement de désactivation de clé incohérent. | Extraire dans `services/exchange_error_classifier.py`, importer des deux côtés. |
| B05 | 🟠 | `app/services/insights_service.py` (403) + `app/services/smart_insights_service.py` (1 525) + endpoints `insights.py` & `smart_insights.py` | Deux systèmes d'insights parallèles, deux endpoints, recouvrement fonctionnel probable. | Confusion sur la source de vérité, double maintenance, code mort potentiel (l'ancien `insights` peut-être obsolète). | Confirmer lequel est vivant ; déprécier/supprimer l'ancien ou fusionner sous une interface commune. |
| B06 | 🟠 | `frontend/src/pages/ExchangesPage.tsx` (2 185 LOC) | Page-composant monolithique (dialogs, formulaires clés, tableaux d'actifs, sync, cold wallets). | Re-renders coûteux, état local difficile à suivre, réutilisation nulle. | Découper en sous-composants (`ApiKeyForm`, `ApiKeyList`, `SyncStatusCard`, `ColdWalletSection`) + hooks dédiés. |
| B07 | 🟠 | `frontend/src/pages/*` — 10/36 pages seulement gèrent `isError`/`error` de React Query | 26 pages n'affichent pas d'état d'erreur explicite sur leurs requêtes. | En cas d'échec API (cold start Render, 500), l'utilisateur voit un écran vide ou un spinner infini, pas de message. | Composant `<QueryErrorState>` réutilisable + convention "toute `useQuery` rend un état d'erreur". |

### 🟡 Mineur

| ID | Sév | Fichier:ligne | Problème | Risque | Reco |
|----|-----|---------------|----------|--------|------|
| C01 | 🟡 | `frontend/package.json:17-21,45` | Deux libs de graphes : `@nivo/*` (5 paquets : bar/core/line/pie/radar) **et** `lightweight-charts`. | Bundle gonflé, incohérence visuelle, double courbe d'apprentissage. | Choisir une lib par cas d'usage (nivo = dashboards, lightweight = prix temps réel) et documenter, ou consolider. |
| C02 | 🟡 | `frontend/package.json:16-55` | Versions en `^` (caret) sur la quasi-totalité des deps applicatives (axios, zustand, react-query, zod…), seules Radix/framer-motion épinglées. | Builds non-reproductibles, drift silencieux entre environnements. | S'appuyer sur le lockfile (présent) + envisager le pinning strict des deps critiques (react-query, axios, zod). |
| C03 | 🟡 | `frontend/src/components/charts/*` (`['platform-distribution']`, `PlatformSelect.tsx` `['user-platforms']`, `DashboardMunitionsCard.tsx` `['dashboard','munitions']`) | ~14 `queryKey` hardcodés contournent la factory centralisée `lib/queryKeys.ts`. | Invalidation incohérente : un `invalidateQueries(queryKeys.…)` ne touchera pas ces clés → caches périmés affichés. | Migrer toutes les clés vers `queryKeys`. |
| C04 | 🟡 | `app/services/metrics_service.py` (2 127), `report_service.py` (2 744), `analytics_service.py` (2 111) | God-services secondaires (cf. B01). | Mêmes risques que B01 à moindre échelle. | Découpage progressif par fonction (calcul / agrégation / formatage). |
| C05 | 🟡 | `frontend/src` — 43 fichiers utilisent `toLocaleString`/`Intl.NumberFormat`/`formatCurrency` | Formatage monétaire dispersé plutôt que centralisé. | Incohérences d'affichage (devise, décimales) entre pages. | Forcer le passage par un unique `lib/utils.formatCurrency`. |
| C06 | 🟡 | `app/tasks/import_history.py:15-28`, `price_updates.py:70-89` | Logique `get_event_loop`/`is_running`/fallback `RuntimeError` recopiée et fragile (anti-pattern Python 3.10+). | Code dupliqué + comportement indéfini si appelé dans un contexte déjà async. | Helper unique (cf. A01). |

### 🔵 Info / observations positives

| ID | Sév | Élément | Note |
|----|-----|---------|------|
| D01 | 🔵 | `app/core/config.py` | Très propre : `SECRET_KEY`/`FERNET_KEY` sans défaut + validators, `COOKIE_SECURE` auto selon `APP_ENV`, gestion asyncpg/sslmode robuste. À conserver comme référence. |
| D02 | 🔵 | `frontend/src/stores/authStore.ts:149` | `partialize` ne persiste que `isAuthenticated`, tokens en cookie httpOnly, ré-hydratation via `hydrateSession`. Bonne pratique sécurité. (Mineur : `fetchUser` est un alias mort de `fetchCurrentUser`.) |
| D03 | 🔵 | `frontend/src` typage | 4 `any` au total, tous des génériques légitimes (`lazyWithRetry<T extends ComponentType<any>>`). Typage TS excellent. |
| D04 | 🔵 | `backend/tests` (44 fichiers) | Couverture domaine forte : xirr, monte-carlo withdrawals, stress ML, parités (value/liquidity/dashboard), cohérence régimes. Services majeurs tous couverts (prediction/report/metrics/analytics). |
| D05 | 🔵 | `frontend/src/App.tsx` + `lib/lazyWithRetry.ts` | Toutes les routes en `lazy` avec retry sur échec de chunk. Bon code-splitting. |
| D06 | 🔵 | `app/models/transaction.py` | Modèle soigné : index partiels, CheckConstraints (quantity/price/fee ≥ 0), hash de dédup déterministe documenté. |
| D07 | 🔵 | TODO/FIXME = 3 au total | Dette explicitement marquée quasi inexistante (le seul vrai : `project_document.py:30`, migration object storage). |

---

## Dette technique cumulée

- **God-files** : ~13 fichiers > 1 000 LOC (8 backend, 5 frontend). À eux seuls, les 4 plus gros services backend pèsent **~10 700 LOC** soit 21 % du backend. Le coût de modification croît de façon non-linéaire ; chaque feature touchant ces fichiers est risquée.
- **Couche de données manuelle** : l'absence totale de relations ORM est une dette de fondation. Migrer demande de toucher tous les `select()` manuels mais débloque eager loading + intégrité + lisibilité. À faire avant que le nombre de requêtes ne devienne ingérable.
- **Gestion d'erreurs permissive** : 352 `except Exception`, 47 `: pass`, 31 swallow en `logger.debug`. Beaucoup sont défendables (best-effort sur pub/sub, prix optionnels), mais la frontière entre "best-effort acceptable" et "erreur financière avalée" (A02) n'est pas tracée. Risque de bugs silencieux.
- **Duplication async tasks** : 7 helpers de boucle quasi-identiques + `_classify_and_mark_error` en double. Symptôme d'absence de couche partagée pour les tâches Celery.
- **Endpoints god** : `transactions.py`, `api_keys.py`, `dashboard.py` contiennent de la logique métier qui devrait vivre en service — empêche la réutilisation par Celery et durcit les tests.

---

## Quick wins (fort ROI, faible effort)

1. **(A01/C06)** Centraliser **un seul** `run_async` dans `app/tasks/__init__.py` et configurer l'engine worker en `NullPool` (ou `asyncio.run` partout). Élimine 7 copies + une classe de bugs prod intermittents. **~1 j.**
2. **(A02)** Remplacer les 3 `except Exception: pass` de `metrics_service.py` (l. 402, 1325, 1524) par log + flag `partial`/`stale` dans la réponse. Corrige des valeurs financières silencieusement fausses. **~0.5 j.**
3. **(B04)** Factoriser `_classify_and_mark_error` dans un module partagé. **~1 h.**
4. **(C03)** Migrer les 14 `queryKey` hardcodés vers `lib/queryKeys.ts` → invalidation de cache fiable. **~2 h.**
5. **(B07)** Composant `<QueryErrorState>` + l'ajouter sur les pages critiques (dashboard, portfolio, transactions, exchanges). **~1 j.**
6. **(D02)** Supprimer l'alias mort `fetchUser` dans `authStore.ts`. **~5 min.**
7. **(C01)** Décider de la stratégie charts (nivo vs lightweight) et retirer la lib non utilisée du bundle. **~0.5 j** (selon usage réel).

---

## Synthèse (< 300 mots)

**Note de santé du code : 6.5 / 10.**

InvestAI a des fondations sécurité/config/typage/tests bien meilleures que la moyenne (config sans secrets par défaut, store auth sans persistance de tokens, 4 `any` seulement en TS, 44 fichiers de tests backend orientés domaine financier, code-splitting complet). La note est tirée vers le bas par la dette structurelle : god-files, couche de données entièrement manuelle, et gestion d'erreurs trop large.

**Findings : 2 🔴 · 7 🟠 · 6 🟡 · 7 🔵 (positifs).**

**Top 3 problèmes structurels :**

1. **God-files.** `services/prediction_service.py:1` (3 733 LOC), `services/report_service.py` (2 744), `services/metrics_service.py` (2 127), `api/v1/endpoints/api_keys.py` (1 692), `pages/ExchangesPage.tsx` (2 185). ~13 fichiers > 1 000 LOC. Maintenabilité et testabilité fortement dégradées.
2. **Couche de données 100 % manuelle.** Zéro `relationship()` sur tous les modèles (`models/portfolio.py:12` n'a aucune relation) ; logique SQL dans les endpoints (`api/v1/endpoints/transactions.py` = 70 requêtes directes) ; aucun `selectinload`/`joinedload` → pas d'eager loading, surface N+1.
3. **Erreurs avalées + duplication async.** `services/metrics_service.py:402,1325,1524` avalent silencieusement des échecs de taux de change (valeur portefeuille faussée). 7 helpers `new_event_loop` dupliqués dans `app/tasks/` réutilisent l'engine async global (`core/database.py:14`) → risque "Future attached to a different loop" asyncpg. `_classify_and_mark_error` dupliqué entre `tasks/sync_exchanges.py:39` et `endpoints/api_keys.py:27`.

Les quick wins (helper async unique, fix des 3 swallow financiers, migration des `queryKey`, état d'erreur React) offrent un fort ROI sous ~3 jours.
