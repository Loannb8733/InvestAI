import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import NavRail from './NavRail'

vi.mock('@/stores/authStore', () => ({
  useAuthStore: (selector: (s: unknown) => unknown) => selector({ user: { role: 'user' } }),
}))

function renderRail(url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <NavRail />
    </MemoryRouter>
  )
}

/** Le rail est rendu deux fois (barre fixe + tiroir mobile, `inert` fermé). */
function libellesCourants() {
  return Array.from(document.querySelectorAll('[aria-current="page"]')).map((n) =>
    (n.textContent || '').trim()
  )
}

/**
 * React Router allume un `NavLink` par correspondance de préfixe. Sur
 * /crowdfunding/audit-lab, « Mes Projets » (/crowdfunding) s'allumait donc en
 * même temps qu'« Audit Lab » : deux entrées surlignées, et deux
 * `aria-current="page"` là où la spécification n'en admet qu'un.
 */
describe('NavRail — entrée active', () => {
  it("n'allume que l'Audit Lab sur sa propre page", () => {
    renderRail('/crowdfunding/audit-lab')
    const courants = new Set(libellesCourants())
    expect(courants).toEqual(new Set(['Audit Lab']))
  })

  it("n'allume que Mes Projets sur /crowdfunding", () => {
    renderRail('/crowdfunding')
    expect(new Set(libellesCourants())).toEqual(new Set(['Mes Projets']))
  })

  it("n'allume pas l'accueil sur une autre page", () => {
    renderRail('/portfolio')
    expect(new Set(libellesCourants())).toEqual(new Set(['Portefeuille']))
  })

  it('désigne une seule page courante, quelle que soit la route', () => {
    for (const url of ['/', '/crowdfunding', '/crowdfunding/audit-lab', '/portfolio', '/notes']) {
      const { unmount } = renderRail(url)
      // Un libellé distinct : les doublons viennent des deux rendus du rail.
      expect(new Set(libellesCourants()).size, `sur ${url}`).toBe(1)
      unmount()
    }
  })

  it('reste allumé sur une sous-route non listée au rail', () => {
    // /notes n'a pas d'entrée descendante : l'activation par préfixe est
    // conservée, pour qu'une fiche ouverte depuis la liste garde son repère.
    renderRail('/notes/42')
    expect(new Set(libellesCourants())).toEqual(new Set(['Journal']))
  })
})
