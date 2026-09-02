import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

/**
 * UX-09 et UX-03 — la première page vue doit être juste, et ressembler au reste.
 *
 * Le titre du Login était le seul de l'application à ne pas être en serif. Sa
 * page jumelle, Register, l'était déjà au même endroit : ce n'était pas un
 * choix, c'était un oubli.
 *
 * Plus gênant, la page annonçait « Actions » parmi les univers couverts — la
 * même promesse sans parcours que le guide de démarrage. Sur l'écran de
 * connexion, c'est la toute première chose qu'un visiteur lit.
 */

const lire = (f: string) => readFileSync(resolve(process.cwd(), 'src/pages', f), 'utf-8')
const LOGIN = lire('LoginPage.tsx')
const REGISTER = lire('RegisterPage.tsx')

const sansCommentaires = (s: string) =>
  s.replace(/\{\/\*[\s\S]*?\*\/\}/g, '').replace(/\/\/.*$/gm, '')

describe('Cohérence typographique des pages d\'entrée', () => {
  it('le titre du Login est en serif, comme partout ailleurs', () => {
    const h1 = LOGIN.match(/<h1 className="([^"]*)"/)?.[1] ?? ''
    expect(h1, 'titre du Login').toMatch(/font-serif/)
  })

  it('Login et Register titrent de la même façon', () => {
    const titre = (s: string) => s.match(/<h1 className="([^"]*)"/)?.[1] ?? ''
    for (const cls of ['font-serif', 'font-medium']) {
      expect(titre(LOGIN), `Login devrait porter ${cls} comme Register`).toContain(cls)
      expect(titre(REGISTER), `Register porte ${cls}`).toContain(cls)
    }
  })
})

describe('La page d\'entrée n\'annonce que ce qui existe', () => {
  const univers = LOGIN.match(/const univers = \[([^\]]*)\]/)?.[1] ?? ''

  it('la liste des univers a bien été trouvée', () => {
    // Un regex qui ne matche plus rendrait les assertions suivantes vides.
    expect(univers.length).toBeGreaterThan(10)
  })

  it('ne promet ni Actions, ni ETF, ni Immobilier', () => {
    for (const absent of ['Actions', 'ETF', 'Immobilier']) {
      expect(univers, `« ${absent} » n'a aucun parcours dans l'application`).not.toContain(absent)
    }
  })

  it('mentionne crypto et crowdfunding', () => {
    expect(univers).toMatch(/Crypto/)
    expect(univers).toMatch(/Crowdfunding/)
  })

  it('le texte d\'accroche ne cite pas non plus les actions', () => {
    const corps = sansCommentaires(LOGIN)
    expect(corps).not.toMatch(/Crypto, actions,/)
  })
})
