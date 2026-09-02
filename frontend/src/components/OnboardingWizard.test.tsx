import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

/**
 * UX-03 — le guide de démarrage ne doit promettre que ce qui existe.
 *
 * Il annonçait quatre catégories : Crypto, Actions, ETF, Immobilier. Trois
 * n'ont aucun parcours dans l'application — ni page, ni formulaire, ni type
 * d'actif utilisé. Et il passait sous silence le Crowdfunding, qui lui existe :
 * six projets, cinquante-neuf échéances.
 *
 * Une promesse fausse au premier écran est plus coûteuse qu'une fonctionnalité
 * manquante : elle donne à croire que l'outil ne marche pas, plutôt qu'il ne
 * fait pas cela.
 *
 * Second volet : le guide vivait sur `/crypto`, où un nouveau venu n'arrive
 * jamais — la route d'accueil est `/`, servie par MasterDashboardPage. Il ne
 * s'affichait donc pour personne.
 */

const lire = (chemin: string) => readFileSync(resolve(process.cwd(), chemin), 'utf-8')

const SOURCE = lire('src/components/OnboardingWizard.tsx')
const ACCUEIL = lire('src/pages/MasterDashboardPage.tsx')
const CRYPTO = lire('src/pages/DashboardPage.tsx')

// Les cartes de la première étape, telles qu'affichées.
const cartes = [...SOURCE.matchAll(/label: '([^']+)'/g)].map((m) => m[1])

describe('Les catégories annoncées existent', () => {
  it('ne promet ni Actions, ni ETF, ni Immobilier', () => {
    const absents = cartes.filter((c) => ['Actions', 'ETF', 'Immobilier'].includes(c))
    expect(absents, "catégorie annoncée sans parcours dans l'application").toEqual([])
  })

  it('mentionne le crowdfunding, qui existe', () => {
    expect(cartes.some((c) => /crowdfunding/i.test(c))).toBe(true)
  })

  it('mentionne la crypto, qui est le cœur de l\'outil', () => {
    expect(cartes.some((c) => /crypto/i.test(c))).toBe(true)
  })

  it('ne cite pas de produit inexistant dans les exemples', () => {
    // « Actions PEA » était donné en exemple de nom de portefeuille.
    expect(SOURCE).not.toMatch(/Actions PEA/)
  })
})

describe('Le guide est monté là où arrive un nouveau venu', () => {
  it('est monté sur la page d\'accueil', () => {
    expect(ACCUEIL).toMatch(/<OnboardingWizard/)
    expect(ACCUEIL).toMatch(/useOnboarding/)
  })

  it('son affichage dépend bien de l\'état du guide', () => {
    // Vérifier la seule présence du composant ne suffit pas : remplacer la
    // condition par `false` laissait le test au vert alors que le guide ne
    // s'affichait plus. Constaté par canari.
    const rendu = ACCUEIL.slice(ACCUEIL.indexOf('return ('))
    expect(rendu).toMatch(/\{onboardingVisible && \(/)
    expect(ACCUEIL).toMatch(/useState\(showOnboarding\)/)
  })

  it('n\'est plus monté sur /crypto', () => {
    // Deux montages afficheraient le guide deux fois avant qu'il soit terminé.
    expect(CRYPTO).not.toMatch(/<OnboardingWizard/)
  })

  it('utilise la même clé de stockage qu\'avant le déplacement', () => {
    // `user.email` au lieu de `user.id` aurait fait réapparaître le guide à
    // tous ceux qui l'avaient déjà terminé.
    expect(ACCUEIL).toMatch(/useOnboarding\(userId\)/)
    expect(ACCUEIL).toMatch(/s\.user\?\.id/)
  })
})
