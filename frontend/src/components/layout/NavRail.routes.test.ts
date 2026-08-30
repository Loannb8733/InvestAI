import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { navGroups } from './navigation'
import { LEGACY_TAB_MAP, TABS } from '@/pages/intelligenceTabs'

/**
 * UX-01 — le menu ne doit jamais mener à la 404.
 *
 * On croise les chemins déclarés dans le NavRail avec les <Route> de App.tsx,
 * lu comme source : monter <App /> exigerait de mocker toute la couche API,
 * alors que la régression à verrouiller est purement déclarative (une entrée
 * de menu ajoutée sans sa route).
 */

// jsdom sert import.meta.url en http: — on repart de la racine du projet.
const appSource = readFileSync(resolve(process.cwd(), 'src/App.tsx'), 'utf-8')

/** Chemins absolus servis par une <Route> (les enfants sont relatifs à "/"). */
const declaredRoutes = new Set(
  [...appSource.matchAll(/path="([^"]+)"/g)].map(([, path]) =>
    path.startsWith('/') ? path : `/${path}`,
  ),
)

/** path de la route → cible de son <Navigate to="..."> quand c'en est une. */
const redirects = new Map(
  [...appSource.matchAll(/path="([^"]+)"\s+element=\{<Navigate\s+to="([^"]+)"/g)].map(
    ([, from, to]) => [from.startsWith('/') ? from : `/${from}`, to],
  ),
)

const navItems = navGroups.flatMap((group) =>
  group.items.map((item) => ({ ...item, group: group.label })),
)

describe('NavRail → routes', () => {
  it.each(navItems)('« $label » ($path) est servi par une route', ({ path }) => {
    expect(declaredRoutes).toContain(path)
  })

  it.each(navItems.filter((item) => redirects.has(item.path)))(
    '« $label » redirige vers un onglet existant',
    ({ path }) => {
      const target = redirects.get(path)!
      const [pathname, query] = target.split('?')
      expect(declaredRoutes).toContain(pathname)

      const tab = new URLSearchParams(query ?? '').get('tab')
      if (pathname === '/intelligence' && tab) {
        const known =
          TABS.some((t) => t.value === tab) ||
          Object.prototype.hasOwnProperty.call(LEGACY_TAB_MAP, tab)
        expect(known, `onglet "${tab}" inconnu de IntelligencePage`).toBe(true)
      }
    },
  )

  it('« Stratégies » atterrit sur le pilier Décisions', () => {
    const strategies = navItems.find((item) => item.label === 'Stratégies')
    expect(strategies?.path).toBe('/strategies')
    expect(redirects.get('/strategies')).toBe('/intelligence?tab=strategies')
    expect(LEGACY_TAB_MAP.strategies).toBe('decisions')
    expect(TABS.map((t) => t.value)).toContain('decisions')
  })
})
