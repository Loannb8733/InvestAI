import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * UX-04 — convention : toute page critique rend un état d'erreur.
 *
 * Une `useQuery` qui rejette ne lève rien pendant le rendu : le RouteErrorBoundary
 * ne la rattrape pas. Sans état explicite, la page reste vide ou tourne
 * indéfiniment, et l'utilisateur ne peut ni comprendre ni réessayer.
 *
 * On lit la source plutôt que de monter les pages : les monter exigerait de mocker
 * toute la couche API, alors que la régression à verrouiller est déclarative —
 * une page critique qui interroge l'API sans prévoir l'échec.
 */

const CRITIQUES = ['DashboardPage', 'CalendarPage', 'MasterDashboardPage', 'NotesPage'] as const

const source = (page: string) =>
  readFileSync(resolve(process.cwd(), `src/pages/${page}.tsx`), 'utf-8')

const composant = () =>
  readFileSync(resolve(process.cwd(), 'src/components/ui/query-error-state.tsx'), 'utf-8')

describe('états d’erreur des pages critiques', () => {
  it.each(CRITIQUES)('%s interroge bien l’API', (page) => {
    // Garde-fou : si la page cesse d'utiliser useQuery, le test suivant
    // passerait à vide et ne protégerait plus rien.
    expect(source(page)).toContain('useQuery')
  })

  it.each(CRITIQUES)('%s rend un état d’erreur', (page) => {
    // On cherche un USAGE, pas un import : `import QueryErrorState …` resté en
    // place après suppression du rendu suffisait à valider le test à tort.
    const src = source(page)
    const gere = /<QueryErrorState|isError|error &&|error \?/.test(src)
    expect(gere, `${page} n’affiche rien quand sa requête échoue`).toBe(true)
  })

  it('le composant partagé propose de réessayer', () => {
    expect(composant()).toContain('onRetry')
    // Il s'appuie sur EmptyState : une seule apparence pour tous les états de page.
    expect(composant()).toContain('EmptyState')
  })

  it('le détail technique reste masqué en production', () => {
    // Un message d'exception expose des chemins et des internes (cf. SEC-02).
    expect(composant()).toContain('import.meta.env.DEV')
  })
})
