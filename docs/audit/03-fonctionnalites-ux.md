# Audit 03 — Produit / Fonctionnalités & UX — InvestAI

> Périmètre : 36 pages `frontend/src/pages/` + `components/` (layout, ui, charts, forms, crowdfunding…).
> Méthode : lecture du routeur (`App.tsx`), du shell de navigation (`Layout`, `NavRail`, `Header`, `Breadcrumb`), des 4 pages « conteneurs » à onglets et d'un échantillon couvrant tous les domaines fonctionnels (dashboard global/crypto, portfolio, transactions, exchanges, intelligence, prédictions, stratégies, objectifs, simulations, alertes, rapports, paramètres, crowdfunding, auth, onboarding).
> Lecture seule — aucune modification.

---

## Résumé exécutif

L'application a subi une **consolidation d'architecture réussie** : 36 « pages » historiques sont désormais regroupées derrière ~12 routes via des conteneurs à onglets (`PortfolioUnifiedPage`, `IntelligencePage`, `StrategyPage`, `CrowdfundingMesProjectsPage`) et des redirections d'anciennes URLs. Le **système de design est authentiquement premium** : tokens OKLCH dark/light, sémantique financière dédiée (gain/loss/warning), titres serif éditorial (Newsreader) + chiffres tabulaires JetBrains Mono, utilitaires `glow`/`glass`/`mesh`, `prefers-reduced-motion` global. C'est une vraie identité « private bank », pas un template shadcn générique.

Mais la consolidation est **inachevée et incohérente** : la sidebar pointe vers des routes mortes ou redirigées, la taxonomie « Objectifs / Stratégies / Stratégie » est dédoublée sur 3 emplacements, les pages internes des onglets ré-affichent leur propre `<h1>` (triple titrage), et l'onboarding + les rapports promettent des classes d'actifs (actions, ETF, immobilier) que le produit ne gère pas.

| Note | Score | Justification |
|------|-------|---------------|
| **UX globale** | **6,5 / 10** | Features riches et complètes, mais navigation cassée/redondante et états d'erreur peu couverts. |
| **Identité design** | **8,5 / 10** | Direction « Flux » cohérente, audacieuse, soignée. Pénalisée seulement par un titrage dupliqué dans les onglets et `font-serif` non appliqué au h1 du login. |

### Top 3 frictions
1. **🔴 Lien sidebar « Stratégies » → `/strategies` = 404.** La route n'existe pas (`App.tsx` n'a ni route ni redirect pour `strategies`). Clic garanti vers la page 404 en production.
2. **🔴 Triple titrage dans les conteneurs à onglets.** Breadcrumb + label d'onglet + `<h1>` de la page interne disent tous la même chose (ex. `/intelligence?tab=analytics` → « Analyses IA » / onglet « Analyses » / h1 « Analyses »).
3. **🟠 Onboarding & rapports mentent sur le périmètre.** Le wizard et la page Rapports vendent « Actions, ETF, Immobilier/SCPI, déclaration valeurs mobilières » alors que l'app ne gère que crypto + crowdfunding.

---

## Findings par sévérité

### 🔴 Critique

| ID | Sév. | Page / Composant | Problème | Impact UX | Reco |
|----|------|------------------|----------|-----------|------|
| F-01 | 🔴 | `components/layout/NavRail.tsx:67` + `App.tsx` | Item de menu « Stratégies » → `/strategies` : aucune route ni redirect → catch-all **404**. | Entrée de menu principale cassée en prod ; perte de confiance immédiate. | Soit pointer vers `/intelligence?tab=strategies` (emplacement réel), soit ajouter `<Route path="strategies" element={<Navigate to="/intelligence?tab=strategies" replace/>}/>`. |
| F-02 | 🔴 | `IntelligencePage.tsx` + `PortfolioUnifiedPage.tsx` + `StrategyPage.tsx` + inner pages | Chaque page interne (`AnalyticsPage`, `InsightsPage`, `TransactionsPage`, `CrowdfundingDashboardPage`…) garde son propre `<h1 className="text-3xl font-serif">`, rendu **sous** le Breadcrumb + le label d'onglet du conteneur. Triple titrage redondant. | Hiérarchie visuelle confuse, scroll inutile, look « pages empilées » plutôt qu'app unifiée. | Faire des pages internes des composants « contenu » sans header ; déplacer le titre unique dans le conteneur (ou conditionner le `<h1>` via une prop `embedded`). |
| F-03 | 🔴 | `components/OnboardingWizard.tsx:35-48,93-96` + `pages/ReportsPage.tsx:354-369` | Onboarding promet « Actions, ETF, Immobilier, SCPI » ; Rapports propose « déclaration valeurs mobilières (actions, ETF, obligations) ». Le produit ne gère **que crypto + crowdfunding**. | Promesse non tenue → frustration dès le 1er écran ; rapports fiscaux « actions » potentiellement vides/trompeurs. | Aligner le wizard et les rapports sur le périmètre réel (crypto + crowdfunding), ou masquer les cartes actions/ETF tant que la feature n'existe pas. |

### 🟠 Majeur

| ID | Sév. | Page / Composant | Problème | Impact UX | Reco |
|----|------|------------------|----------|-----------|------|
| F-04 | 🟠 | `OnboardingWizard` (monté **uniquement** dans `DashboardPage.tsx:492`, route `/crypto`) | L'index `/` est `MasterDashboardPage`, qui n'instancie **pas** le wizard. Un nouvel utilisateur atterrit sur `/` et **ne voit jamais l'onboarding** sauf s'il navigue manuellement vers `/crypto`. | Le guide d'accueil, pourtant soigné, est quasi inatteignable pour la majorité des nouveaux comptes. | Monter `OnboardingWizard` au niveau `Layout` (ou sur `/`) plutôt que dans `DashboardPage`. |
| F-05 | 🟠 | Taxonomie « Stratégie/Stratégies/Objectifs » | `/strategy` (= Objectifs+Simulations) vs `/strategies` (= rebalancing IA, dans onglet Intelligence) vs onglet « Stratégie » de `ReportsPage` (RebalancingTab). 3 emplacements, noms quasi identiques (`strategy` ≠ `strategies`). | Modèle mental impossible à former ; collision d'URL au singulier/pluriel. | Renommer : « Objectifs » (route `/goals`) et « Stratégies de rebalancing » (route unique `/strategies`). Supprimer le doublon RebalancingTab des Rapports ou le transformer en lien. |
| F-06 | 🟠 | Gestion d'erreur des requêtes | Seules ~5 pages sur 36 gèrent `isError`/affichent un retry (`AnalyticsPage`, `SmartInsightsPage`, `InsightsPage`, `CrowdfundingAuditLabPage`, `VerifyEmailPage`). Les autres rendent un vide/blank si l'API échoue (le `RouteErrorBoundary` ne capte que les exceptions JS, pas une query en `error`). | En cas d'erreur réseau/API, l'utilisateur voit une page vide sans explication ni bouton « Réessayer ». | Standardiser un composant `<QueryError onRetry={refetch}/>` et le brancher sur chaque `useQuery` critique. |
| F-07 | 🟠 | `MasterDashboardPage.tsx:578` | Raccourci « Signaux Alpha » navigue vers `/intelligence?tab=predictions`, alors que les Signaux Alpha sont l'onglet **`alpha`** (défaut). Label ≠ destination. | L'utilisateur clique « Signaux Alpha » et arrive sur l'onglet Prédictions. | Corriger la cible en `/intelligence` (ou `?tab=alpha`). |
| F-08 | 🟠 | `DashboardPage.tsx` vs `MasterDashboardPage.tsx` | Deux dashboards aux KPIs très proches (patrimoine, P&L, allocation, courbe de perf) mais traitements divergents : MasterDashboard = skeleton + framer-motion + récit narratif ; Dashboard (`/crypto`) = spinner `Loader2`, widgets drag-drop, mode privacy, WebSocket live, benchmarks, export PDF. | Redondance perçue + incohérence de loading/animations entre deux écrans « tableau de bord ». | Voir section « pages redondantes ». Clarifier : `/` = patrimoine global (read-only narratif), `/crypto` = cockpit crypto interactif. Harmoniser skeleton vs spinner. |

### 🟡 Mineur

| ID | Sév. | Page / Composant | Problème | Impact UX | Reco |
|----|------|------------------|----------|-----------|------|
| F-09 | 🟡 | Loading states | 29 pages utilisent un spinner `Loader2` plein écran ; seules 5 utilisent un skeleton (`MasterDashboard`, etc.). | Saut de mise en page + perception de lenteur vs skeletons. | Généraliser les skeletons sur les écrans à structure connue (tables, KPI rows). |
| F-10 | 🟡 | `components/layout/Breadcrumb.tsx` + conteneurs | Les fils d'Ariane ne passent jamais de `path` → tous les segments sont du texte mort, non cliquables. | « Fil d'Ariane » décoratif, ne permet pas de remonter. | Rendre le 1er segment cliquable (ex. « Univers Crypto » → `/`). |
| F-11 | 🟡 | `CrowdfundingMesProjectsPage.tsx:36` | Breadcrumb figé « Crowdfunding > Mes Projets » quel que soit l'onglet actif, alors que `StrategyPage` met à jour son breadcrumb par onglet. | Incohérence entre conteneurs ; le breadcrumb ne reflète pas la vue. | Aligner sur le pattern `TAB_LABELS` de `StrategyPage`. |
| F-12 | 🟡 | `ReportsPage.tsx:315` | Utilise `<Tabs defaultValue>` (état local, non synchronisé à l'URL) là où tous les autres conteneurs synchronisent l'onglet via `useSearchParams`. | Pas de deep-link ni de retour arrière sur l'onglet rapports. | Synchroniser via `?tab=`. |
| F-13 | 🟡 | `LoginPage.tsx:93` | Le h1 du login utilise `font-semibold` (sans-serif) alors que toute l'app titre en `font-serif` (Newsreader). | Première impression légèrement hors-charte. | Appliquer `font-serif` pour cohérence de marque dès le login. |
| F-14 | 🟡 | `components/layout/Header.tsx:39` | Header quasi vide (commentaire « Breadcrumb or page title could go here ») ; pas de titre de page ni de recherche globale dans la barre supérieure. | Espace gâché, pas de repère contextuel persistant en haut. | Y afficher le breadcrumb/titre courant, voire une recherche globale (cmd-K déjà présent dans `ui/command.tsx`). |

### 🔵 Observations / pistes

| ID | Sév. | Page / Composant | Problème | Impact UX | Reco |
|----|------|------------------|----------|-----------|------|
| F-15 | 🔵 | `index.css:201` + `MasterDashboardPage` | `prefers-reduced-motion` couvre les transitions/animations **CSS**, mais pas les animations **JS framer-motion** (opacity/y, stagger) de MasterDashboard et Login. | Utilisateurs sensibles au mouvement gardent les entrées animées. | Brancher `useReducedMotion()` (déjà utilisé dans les charts) sur les `motion.*` des deux pages. |
| F-16 | 🔵 | `NavRail.tsx:194` | Rail desktop replié à 76 px, qui s'**étend au survol** (overlay) à 256 px. Les labels n'apparaissent qu'au hover (`opacity-0 group-hover:opacity-100`). | Découvrabilité réduite : icônes seules sans texte tant qu'on ne survole pas ; pas idéal au clavier/tactile. | Ajouter une option « épingler étendu », et garantir l'affichage des labels au focus clavier (`group-focus-within`). |
| F-17 | 🔵 | `crowdfunding` (5 pages) | Bonne séparation Dashboard/Projets/Performance/Audit Lab, mais « Audit Lab » est une route à part (`/crowdfunding/audit-lab`) alors que les 3 autres sont des onglets. Asymétrie. | Légère rupture de modèle (onglets vs route dédiée). | Soit intégrer Audit Lab comme 4e onglet, soit assumer la séparation (probablement justifiée car flux long). |

---

## Pages redondantes / à consolider

| Groupe | Pages | Verdict | Reco |
|--------|-------|---------|------|
| **Dashboards** | `MasterDashboardPage` (`/`), `DashboardPage` (`/crypto`) | **Redondance partielle assumable.** KPIs et courbe de perf se recoupent, mais les rôles diffèrent : Master = vue patrimoniale globale (crypto + crowdfunding, narratif read-only) ; Dashboard = cockpit crypto interactif (widgets drag-drop, privacy, WebSocket, benchmarks, PDF). | **Garder les deux** mais (a) différencier visuellement le hero, (b) éviter de répéter les mêmes 4 KPI dans le même ordre, (c) harmoniser loading (skeleton partout). Si simplification voulue : fusionner DashboardPage comme onglet « Crypto » du portefeuille et faire de Master l'unique dashboard. |
| **Portfolio** | `PortfolioPage` + `TransactionsPage` + `ExchangesPage` sous `PortfolioUnifiedPage` | **Bonne consolidation.** Onglets cohérents, redirections d'anciennes URLs en place. | RAS — juste retirer les `<h1>` internes (F-02). |
| **Intelligence** | `InsightsPage` + `SmartInsightsPage` + `AnalyticsPage` + `PredictionsPage` + `AlertsPage` + `StrategiesPage` sous `IntelligencePage` | **6 onglets = surcharge.** « Insights » (Signaux Alpha), « Smart Insights » et « Analyses » sont conceptuellement proches → risque de confusion. `StrategiesPage` (rebalancing) n'a rien à faire sous « Analyses IA ». | Regrouper Insights/Smart Insights/Analyses, et **sortir Stratégies** de ce conteneur (lui donner sa propre route, cf. F-05). |
| **Stratégie** | `StrategyPage` (Objectifs+Simulations) vs `StrategiesPage` (rebalancing) vs RebalancingTab des Rapports | **Collision de nommage à 3 endroits.** | Renommer/clarifier (cf. F-05). |
| **Insights doublon** | `InsightsPage` et `SmartInsightsPage` | Noms quasi synonymes, deux entrées d'onglet distinctes. | Renommer en labels métier explicites (« Signaux Alpha » vs « Diagnostic portefeuille »). |

---

## Accessibilité — manquements

| ID | Gravité | Constat | Reco |
|----|---------|---------|------|
| A-01 | 🟠 | `aria-label` présent dans seulement ~5 pages ; 29 boutons `size="icon"` dans pages+composants — vérifier que tous portent un label (Header OK, mais audit à étendre). | Garantir un `aria-label` sur **chaque** bouton icône (suppression, refresh, fermeture, etc.). |
| A-02 | 🟠 | Animations framer-motion (Master, Login) non couvertes par `prefers-reduced-motion` (cf. F-15). | Brancher `useReducedMotion()`. |
| A-03 | 🟡 | Labels du rail visibles uniquement au survol (F-16) → faible support clavier (focus n'ouvre pas le rail). | `group-focus-within:opacity-100` + ordre de tab logique. |
| A-04 | 🟡 | Beaucoup de boutons `h-7`/`h-8` (sélecteurs de période, badges cliquables) sous la cible tactile 44 px recommandée. | Augmenter la zone tactile (padding) sur mobile, ou viser ≥ 40 px. |
| A-05 | 🔵 | Contraste à vérifier : `--gain` light = `0.58 L` (vert) sur fond blanc `0.99 L`, et `text-muted-foreground/70` sur eyebrows — possible < 4.5:1. | Vérifier au contrastomètre ; remonter la luminance des textes secondaires si besoin. |
| A-06 | ✅ | **Points positifs** : `role="navigation"` + `aria-label` sur le menu, `aria-label` sur menu/theme/logout dans Header, breadcrumb en `<nav aria-label="Fil d'Ariane">`, `prefers-reduced-motion` CSS global, aucun `onClick` sur `<div>` nu, tables enveloppées dans `overflow-x-auto`, formulaires auth avec `<Label>` + zod. | — |

---

## Quick wins UX (effort faible, impact élevé)

1. **Ajouter la redirect `/strategies`** (1 ligne dans `App.tsx`) → tue le 404 du menu (F-01).
2. **Corriger la cible du raccourci « Signaux Alpha »** dans MasterDashboard (F-07) → 1 ligne.
3. **Monter l'OnboardingWizard sur `/` (Layout)** au lieu de `/crypto` (F-04) → le guide devient enfin visible.
4. **Conditionner les `<h1>` internes** des pages de tabs via une prop `embedded` (F-02) → supprime le triple titrage partout d'un coup.
5. **Rendre le 1er segment du breadcrumb cliquable** (F-10) → navigation « remonter » gratuite.
6. **Synchroniser l'onglet Rapports à l'URL** (F-12) → deep-link + retour arrière.
7. **`font-serif` sur le h1 du Login** (F-13) → cohérence de marque dès l'entrée.
8. **Aligner onboarding/rapports sur crypto+crowdfunding** (F-03) → supprime la promesse non tenue.

---

## Synthèse (< 300 mots)

**Notes : UX 6,5/10 — Identité design 8,5/10.**

**Findings : 3 🔴, 5 🟠, 5 🟡, 3 🔵** (+ 6 points a11y dont 1 positif).

**Top 3 frictions :**
1. **Lien de menu « Stratégies » → 404** : la route `/strategies` n'existe pas (ni route, ni redirect). Défaut visible en production sur une entrée de navigation principale.
2. **Triple titrage dans les onglets** : Breadcrumb + label d'onglet + `<h1>` de la page interne répètent le même mot. La consolidation en conteneurs à onglets a oublié de retirer les headers des pages embarquées.
3. **Onboarding & Rapports promettent des actifs absents** (actions, ETF, immobilier, SCPI) alors que le produit gère crypto + crowdfunding — promesse non tenue dès le premier écran, et l'onboarding est en plus monté sur la mauvaise route donc rarement vu.

**Mon avis sur la redondance dashboard/portfolio :** la consolidation `PortfolioUnifiedPage` (Résumé/Transactions/Exchanges) est **réussie** et doit servir de modèle. En revanche, **`DashboardPage` (`/crypto`) et `MasterDashboardPage` (`/`) se recoupent** sur les KPIs et la courbe de performance ; ils sont justifiables comme « patrimoine global narratif » vs « cockpit crypto interactif », mais l'utilisateur perçoit deux tableaux de bord jumeaux avec des comportements de chargement et d'animation divergents. Je recommande de **les garder distincts mais de les différencier franchement** (hero, contenu, et harmoniser skeleton/spinner), ou à défaut de fusionner `/crypto` comme onglet du portefeuille. Côté Intelligence, **6 onglets dont 3 quasi-synonymes (Insights / Smart Insights / Analyses)** + une page Stratégies mal classée constituent l'autre gros chantier de clarification.

Le design, lui, est une vraie identité « private bank » assumée (OKLCH, serif éditorial, chiffres mono) — c'est le point fort de l'app.
