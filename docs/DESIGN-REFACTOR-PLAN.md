# InvestAI — Plan de Refactoring Design Complet

> **Statut** : Plan (pré-exécution) · **Date** : 2026-05-30 · **Auteur** : Loann + Claude
> **Objectif** : Refonte totale de l'identité visuelle du frontend pour fuir le look « template/IA générique », créer une identité mémorable et premium, et porter un **storytelling** du parcours patrimonial de l'utilisateur.
> **Périmètre** : `~/projects/InvestAI/frontend/` — Vite + React 18 + TS + React Router v6 + Tailwind v3.4 + shadcn/Radix + recharts + framer-motion. ~36 pages, 27 primitives `ui/`.

---

## 0. Décision structurante — Direction visuelle : **A — Private Bank ✅ (CONFIRMÉE 2026-05-30)**

Trois directions ont été générées via `ui-ux-pro-max`. **Direction A retenue**, car le storytelling repose sur une logique éditoriale (le récit *est* le médium).

| | **A — Private Bank** ⭐ | B — Terminal / Quant | C — Aurora Glass |
|---|---|---|---|
| Base | Ivoire/bone (light) + dark sobre | Dark OLED quasi-noir | Midnight + gradients aurora |
| Accent | Laiton champagne (1 seul) | Mint/rouge/amber sémantique | Gradient indigo→teal |
| Typo titres | Serif éditorial (Newsreader/Libre Bodoni) | Geometric sans + mono | Sans premium (Satoshi/DM Sans) |
| Chiffres | JetBrains Mono | JetBrains Mono partout | JetBrains Mono |
| Personnalité | Discret, wealth, sérieux, **narratif** | Précis, dense, pro | Moderne, vibrant, accessible |
| Risque « générique » | Très faible | Faible | Moyen |
| Affinité storytelling | **Excellente** | Faible | Moyenne |

> ⚠️ Cette décision conditionne les tokens, la typo et le ton. Le reste du document est rédigé pour **A** ; bascule possible vers B/C avant la Phase 1.

---

## 1. Vision & Storytelling (pilier transversal)

**Thèse narrative** : *L'utilisateur est le héros de son parcours patrimonial.* L'app ne montre pas seulement des chiffres — elle **raconte** d'où il part, sa trajectoire, ses caps, ses obstacles et ses victoires.

| Écran | Rôle narratif |
|---|---|
| **Onboarding** | Chapitre 1 — définir ses objectifs = la *destination* du voyage |
| **Dashboard** | « Où en est mon histoire aujourd'hui » — résumé narratif en tête (*« Depuis janvier, ton portefeuille a grandi de X. Ton meilleur actif : Y. »*) |
| **Goals** | Les *caps* à franchir, progression narrée, célébration à l'atteinte |
| **Portfolio / Transactions** | Annotations narratives sur la timeline (*« ici, achat BTC »*) |
| **Predictions / Simulations** | « Et si… ? » — les *futurs possibles* de l'histoire |
| **Reports / Year in Review** | Récap annuel type *Wrapped* du patrimoine |
| **Empty states** | Début d'aventure (*« Ton aventure commence ici »*) |

**Techniques** : progressive disclosure · narration scroll-linked (moments clés) · micro-copy narrative · célébration des milestones · annotations de données contextuelles.

**Skills mobilisés** : `ux-copy`, `ux-flow` (micro-copy & parcours), `antigravity-design-expert` (moments scrollés), `impeccable` (cohérence de marque via `PRODUCT.md`).

---

## 2. Direction A — Spécification

### Palette (OKLCH, neutres teintés vers la teinte de marque — règle Impeccable)
- **Stratégie de couleur** : *Restrained* (neutres teintés + 1 accent ≤ 10 %).
- **Accent** : laiton champagne `#B8893A` (≈ `oklch(0.64 0.10 75)`), unique.
- **Gain / Perte** : vert sapin discret / bordeaux (jamais le néon vert/rouge crypto).
- **Neutres** : ivoire/bone en light, encre profonde teintée en dark (jamais `#000`/`#fff`).
- **À définir précisément en Phase 1** dans `DESIGN.md` + `src/index.css`.

### Typographie
- **Titres / gros chiffres** : Newsreader **ou** Libre Bodoni (serif éditorial, haute lisibilité).
- **Corps / UI** : Public Sans.
- **Chiffres tabulaires** : JetBrains Mono (conservé).

### Motion (curseurs Taste : VARIANCE 8 / MOTION 6 / DENSITY 4 → ajustés)
- Lent, fondu, « coûteux ». Pas de glow néon.
- Moments narratifs scrollés via `antigravity` (parallax léger, entrées staggered).

### Éléments signature
- Valeur de portefeuille traitée comme une **« une » éditoriale** (gros serif).
- Filets fins (hairline rules) comme séparateurs.
- Mise en page « statement » (relevé patrimonial).

---

## 3. Orchestration des skills

| Skill | Statut | Rôle |
|---|---|---|
| `ui-ux-pro-max` | ✅ Windows, testé | Palette, typo, charts, design system |
| `design-taste-frontend` (Taste, Leonxlnx) | ✅ Windows + projet | Garde-fou anti-générique, règles d'implémentation senior |
| `impeccable` | ⚠️ Projet uniquement (`.agents/skills`) | Lois design (OKLCH, registre brand/product), `PRODUCT.md`/`DESIGN.md`, sous-cmds `shape`/`craft`/`audit` via `npx impeccable` |
| `antigravity-design-expert` | ✅ Windows | Motion spatial, scroll-linked, moments narratifs |
| `superpowers` (+lab) | ✅ Windows | Méthode TDD, commits atomiques |
| `unslop`, `avoid-ai-writing`, `/anti-template` | ✅ | Checklist anti look « template IA » par écran |
| `stitch-design-taste`, `gpt-taste` | ✅ | Renfort de jugement esthétique |
| `ui-tokens`, `theme-factory`, `tailwind-design-system` | ✅ | Tokens & thème |
| `shadcn`, `ui-component`, `tailwind-patterns` | ✅ | Re-skin des primitives |
| `ui-page`, `ui-pattern`, `uxui-principles`, `ux-flow`, `ux-copy` | ✅ | Layouts, parcours, micro-copy |
| `ui-review`, `ui-a11y`, `ui-visual-validator`, `ux-audit` | ✅ | QA finale |
| **Awesome Design** | ❌ Introuvable | À réinstaller si souhaité : `npx skills add bergside/awesome-design-skills` |

---

## 4. Plan en 8 phases

### Phase 0 — Identité & contexte de marque
- **Livrables** : direction visuelle confirmée · `PRODUCT.md` (users, brand, **ton narratif**, anti-références, principes) · `DESIGN.md` (couleurs, typo, élévation).
- **Skills** : `impeccable teach`, `ui-ux-pro-max`, `antigravity-design-expert`, `ux-copy`.

### Phase 1 — Design tokens
- Refonte `src/index.css` (variables HSL→OKLCH, sémantique gain/perte) + `tailwind.config.js` (échelle typo, spacing, radii, ombres, motion tokens).
- Conserver le thème dark/light (`.dark`).
- **Skills** : `ui-tokens`, `theme-factory`, `tailwind-design-system`, `impeccable`.

### Phase 2 — Primitives `ui/` (27 composants)
- Re-skin : button, card, badge, input, textarea, label, select, tabs, dialog, alert-dialog, popover, dropdown-menu, tooltip, switch, checkbox, slider, table, command, toast/toaster, skeleton, alert.
- Custom : `animated-number`, `sparkline`, `motion-card`, `crypto-icon`, `asset-icon`.
- **Skills** : `shadcn`, `ui-component`, `tailwind-patterns`, `design-taste-frontend`.

### Phase 3 — Shell & navigation
- `components/layout/` (sidebar, topbar, nav), command palette (`cmdk`), transitions de page.
- **Skills** : `ui-page`, `uxui-principles`, `antigravity-design-expert`.

### Phase 4 — Refonte écran par écran (par impact)
1. **Dashboard / MasterDashboard** (première impression + résumé narratif)
2. **Portfolio / PortfolioUnified**
3. **Analytics / Insights / SmartInsights / Intelligence**
4. **Predictions / Simulations / Strategies / Strategy**
5. **Transactions / Exchanges / Goals / Calendar / Alerts / Notes**
6. **Crowdfunding** (Dashboard, Projects, MesProjects, Performance, AuditLab)
7. **Reports** (+ Year in Review narratif)
8. **Auth** (Login/Register/Forgot/Reset/Verify) + **OnboardingWizard**
9. **Settings / Admin / NotFound**
- **Skills par écran** : `ui-page` + `ui-pattern` + `ux-flow` + `ux-copy`, puis garde-fou `unslop` + `/anti-template` + `design-taste-frontend`, audit `impeccable audit`.

### Phase 5 — Charts (recharts)
- Harmoniser au design system : couleurs sémantiques, grilles discrètes, tooltips éditoriaux, gradients de remplissage.
- Types recommandés (`ui-ux-pro-max` domaine chart) : Line/Area (trend), Streaming Area (temps réel), Bullet/Gauge (performance vs cible), Line + Confidence Band (forecast).
- **Skills** : `ui-ux-pro-max`, `ui-component`.

### Phase 6 — Motion & polish
- Langage framer-motion cohérent, empty states narratifs, skeletons, micro-interactions, célébrations de milestones.
- **Skills** : `antigravity-design-expert`, `design-taste-frontend`.

### Phase 7 — QA design & accessibilité
- Contrastes (≥ 4.5:1), focus visibles, navigation clavier, responsive (375/768/1024/1440), parité dark/light, `prefers-reduced-motion`.
- **Skills** : `ui-review`, `ui-a11y`, `ui-visual-validator`, `ux-audit`.

---

## 5. Règles anti-générique (Taste + Impeccable) — à respecter partout

- **Interdits** : hero centré par défaut, gradient violet cliché, abus de cards, états (hover/focus/empty/error) bâclés, layouts fragiles.
- **Imposés** : Grid > flex-math (`grid-cols-*`), `min-h-[100dvh]` (jamais `h-screen`), conteneur `max-w-[1400px]`/`max-w-7xl`, typo déterministe.
- **Icônes** : Phosphor **ou** Radix uniquement, `strokeWidth` standardisé. **Zéro emoji.**
- **Couleur** : OKLCH, jamais `#000`/`#fff`, neutres teintés vers la teinte de marque, stratégie *Restrained* (1 accent ≤ 10 %).
- **Dépendances** : vérifier `package.json` avant tout import (Taste : DEPENDENCY VERIFICATION).

---

## 6. Méthode d'exécution

- **Itération** : 1 phase = 1 cycle. Validation visuelle avant la suivante.
- **Commits atomiques** (Superpowers) ; pre-commit du repo respecté.
- **Pilote recommandé** : commencer par le **Dashboard** comme proof-of-concept de l'identité A + storytelling, avant de généraliser.
- **Vérification** : `impeccable audit` + `ui-review` en fin de chaque écran.

---

## 7. Risques & dépendances

- **Impeccable hors session Windows** : présent seulement dans `~/projects/InvestAI/.agents/skills/`. Invocation via `npx impeccable` en contexte projet ; sinon application manuelle des règles lues dans son `SKILL.md`.
- **Motion** : `antigravity` recommande GSAP/ScrollTrigger ; la stack utilise **framer-motion 11**. → Soit adapter les patterns à framer-motion (préféré), soit ajouter GSAP (poids supplémentaire).
- **Awesome Design** : non installé. À réinstaller si besoin.
- **Serif sur fond clair** (Direction A) : valider lisibilité des gros chiffres en dark mode.
- **36 pages** : périmètre large → respecter l'ordre par impact, ne pas tout ouvrir en parallèle.

---

## 8. Prochaines étapes

1. **Confirmer la direction** (A recommandée).
2. Lancer **Phase 0** : `impeccable teach` → rédiger `PRODUCT.md` (narration de marque) + `DESIGN.md`.
3. Exécuter **Phase 1** (tokens) puis le **Dashboard pilote** (Phase 4.1) comme preuve de concept.
