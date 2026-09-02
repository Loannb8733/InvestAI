import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { join, resolve } from 'node:path'

/**
 * UX-02 — une page, un seul titre de niveau 1.
 *
 * Huit pages portaient un `<h1>` alors qu'aucune n'est une route : elles ne sont
 * montées que comme onglets d'un conteneur. Sur `/goals`, le mot « Objectifs »
 * apparaissait trois fois — fil d'Ariane, onglet, titre — et deux `<h1>`
 * cohabitaient dans le document.
 *
 * Un lecteur d'écran suit la hiérarchie des titres pour se repérer : deux
 * niveaux 1 dans une page, c'est deux pages annoncées là où il n'y en a qu'une.
 *
 * La correction ne change rien à l'écran : le titre garde ses classes, seule la
 * balise passe en `<h2>`, et le conteneur reçoit un `<h1>` masqué visuellement.
 */

const PAGES = resolve(process.cwd(), 'src/pages')
const lire = (f: string) => readFileSync(join(PAGES, f), 'utf-8')

/** Retire les commentaires : ils citent les balises qu'ils expliquent. */
const sansCommentaires = (s: string) =>
  s.replace(/\{\/\*[\s\S]*?\*\/\}/g, '').replace(/\/\*[\s\S]*?\*\//g, '')

const APP = readFileSync(resolve(process.cwd(), 'src/App.tsx'), 'utf-8')

/** Pages montées comme onglet par un conteneur, et absentes des routes. */
function pagesEnOnglet(): string[] {
  const fichiers = readdirSync(PAGES).filter((f) => f.endsWith('.tsx') && !f.endsWith('.test.tsx'))
  const montees = new Set<string>()
  for (const f of fichiers) {
    for (const m of lire(f).matchAll(/import\('@\/pages\/(\w+)'\)/g)) montees.add(m[1])
  }
  return [...montees].filter((p) => !APP.includes(p))
}

describe('Les onglets ne portent pas de titre de page', () => {
  const enOnglet = pagesEnOnglet()

  it('la liste des pages-onglets n\'est pas vide', () => {
    // Sinon le test ne vérifierait rien tout en restant vert.
    expect(enOnglet.length).toBeGreaterThan(4)
  })

  it.each(pagesEnOnglet())('%s utilise <h2>, pas <h1>', (page) => {
    const source = sansCommentaires(lire(`${page}.tsx`))
    expect(source, `${page} n'est pas une route : son titre est une section`).not.toMatch(/<h1[\s>]/)
  })
})

describe('Chaque conteneur porte le titre de sa page', () => {
  it.each(['PortfolioUnifiedPage', 'StrategyPage', 'CrowdfundingMesProjectsPage', 'IntelligencePage'])(
    '%s déclare un <h1>',
    (conteneur) => {
      const source = sansCommentaires(lire(`${conteneur}.tsx`))
      expect(source, 'sans <h1>, la page démarre au niveau 2 dans l\'arbre d\'accessibilité').toMatch(/<h1[\s>]/)
    }
  )
})
