# VERIF-01 — Vérification du score design par rendu réel

> **Statut** : terminé · **Mode** : lecture seule, rendu local, données **mock client-side** (XHR intercepté sur `/dashboard?` uniquement, jamais la DB prod)
> **Objectif** : confronter le score design **8,5/10** (donné à l'audit UX **sans rendu**) à un rendu réel du `MasterDashboardPage` chargé de données, dark + light.

---

## 1. Méthode

- Backend local (creds locaux, **pas** Supabase prod), user démo jetable créé via API (`verif01-demo@example.com`).
- Le backend local n'a pas de flux de prix → les charts resteraient vides. J'ai donc **mocké uniquement** la réponse `/dashboard?…` côté navigateur (matcher strict `/(\/dashboard\?)/ && !/crowdfunding/` pour ne pas polluer le dashboard crowdfunding).
- Payload synthétique cohérent avec VERIF-02 : patrimoine 84 456 €, investi 57 941 €, P&L net +26 515 € (+45,8 %), rendement annualisé 18,08 %, liquidités 6 950 €, allocation BTC 55,1 / ETH 19,1 / SOL 8,5 / ADA 5,3 / Stablecoins 8,2 / Autres 3,8, 120 points d'historique.
- Vérifications **par `preview_inspect` / DOM** (autoritatif sur styles), pas seulement screenshots (artefact DPR=2 connu).

## 2. Ce qui tient la route (au-dessus du « template shadcn générique »)

- **Hiérarchie typographique éditoriale réelle** : H1 « Patrimoine global » en serif Newsreader, chiffre patrimoine en très gros serif. C'est une signature, pas le sans-serif shadcn par défaut. **Confirmé par inspect** (pas une supposition — j'avais d'ailleurs corrigé une erreur : l'écran de login, lui, est en Public Sans neutre).
- **Palette sombre retenue et non saturée** : pas le « dark fintech bleu néon » cliché. Fond profond, accent violet discret sur le sélecteur de période et le dégradé du graphe.
- **Les charts fonctionnent dans les deux thèmes** : le graphe d'aire « Performance du Capital » (lightweight-charts) se peuple correctement en dark **et** en light. → l'« écran blanc » observé précédemment était un **artefact du mock corrompu** (sur-match crowdfunding), **pas un bug de réactivité au thème**. Je ne signale donc pas de bug ici.
- Cartes KPI lisibles, « Points d'Attention » et « Raccourcis » donnent une vraie densité éditoriale.

## 3. Défauts réels, vérifiés (contre un score élevé)

| # | Défaut | Preuve | Gravité |
|---|---|---|---|
| D1 | **Donut d'allocation monochrome non décodable** | Les **6 arcs** ont le **même** fill `rgb(98,98,106)`, `fill-opacity:1`. Les **6 pastilles de légende** sont **identiques** (`rgb(98,98,106)`). Aucune couleur/teinte/luminance ne distingue BTC d'ETH de SOL… seules les fentes séparent les parts. | **Élevée** — un graphe d'allocation dont le rôle est d'encoder des catégories par couleur n'encode rien. On ne peut pas relier une légende à une part. |
| D2 | **Axes de charts minuscules** | Labels d'axe ~9–10px, contraste faible sur le gris d'arrière-plan. | Moyenne — lisibilité, surtout en clair. |
| D3 | **Logo « sparkle » générique** | Icône d'app par défaut, pas d'identité de marque. | Faible-moyenne — sape le positionnement « private bank ». |
| D4 | Densité d'écran : un seul écran riche vérifié (dashboard). Les ~35 autres pages ne sont pas confirmées sous données réelles. | — | Limite de portée, pas un défaut. |

## 4. Verdict honnête sur le 8,5/10

**Le 8,5/10 est surévalué d'environ 1 à 1,5 point. Score calibré : ~7/10.**

- Le design est **clairement au-dessus** du « template IA générique » sur la typo éditoriale et la retenue chromatique — ce n'est pas contestable et c'est mérité.
- Mais un **8,5** sous-entend un produit quasi sans défaut visible. Or **D1 est un vrai défaut fonctionnel** sur le composant central du tableau de bord (l'allocation), pas une finition cosmétique. Un graphe d'allocation indécodable sur l'écran d'accueil d'une app de patrimoine est exactement le genre de chose qui interdit un 8,5.
- D2/D3 sont des finitions qui, cumulées, retiennent encore le score.

**Conclusion** : la direction artistique est bonne et défendable ; l'exécution sur la dataviz d'allocation ne l'est pas encore. Le score « 8,5 sans rendu » était optimiste. **~7/10 vérifié**, avec un chemin clair vers 8+ : couleurs catégorielles distinctes sur le donut + légende mappée, axes plus grands/contrastés, vraie identité de logo.

## 5. Limites

- Un seul écran chargé (dashboard) ; mock client-side, pas données serveur réelles.
- Light mode forcé via classe `.light` (toggle non testé via l'UI native).
- Pas d'audit a11y complet (contraste AA sur tous les états) ici — le contraste des labels d'axe (D2) est le point le plus probable d'échec AA.
