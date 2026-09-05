import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import Header from './Header'
import { FilDArianeProvider } from './FilDArianeProvider'
import { filParDefaut, useFilDAriane } from './fil-ariane'

// Le Header monte NotificationBell (React Query) et lit le store d'auth.
vi.mock('@/stores/authStore', () => ({
  useAuthStore: (selector: (s: unknown) => unknown) =>
    selector({ user: { role: 'user' }, logout: vi.fn() }),
}))

function renderHeader(url: string, Page?: () => JSX.Element | null) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[url]}>
        <FilDArianeProvider>
          <Header />
          {Page ? <Page /> : null}
        </FilDArianeProvider>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

function fil() {
  return screen.queryByRole('navigation', { name: /fil d'ariane/i })
}

/**
 * UX-10 : cinq pages sur une vingtaine portaient leur propre fil d'Ariane, les
 * quinze autres n'avaient aucun repère, et l'espace gauche du Header était vide.
 */
describe('filParDefaut — dérivé du rail', () => {
  it('donne « groupe › entrée » pour une page du rail', () => {
    expect(filParDefaut('/notes')).toEqual([{ label: 'Outils' }, { label: 'Journal' }])
  })

  it('prend la correspondance la plus longue', () => {
    // /crowdfunding est un préfixe de /crowdfunding/audit-lab : sans cette
    // règle, le fil annoncerait « Mes Projets » sur l'Audit Lab.
    expect(filParDefaut('/crowdfunding/audit-lab')).toEqual([
      { label: 'Crowdfunding' },
      { label: 'Audit Lab' },
    ])
  })

  it("n'attrape pas la racine sur toutes les routes", () => {
    expect(filParDefaut('/portfolio')).toEqual([{ label: 'Crypto' }, { label: 'Portefeuille' }])
  })

  it('rend null pour une route absente du rail', () => {
    expect(filParDefaut('/route-inconnue')).toBeNull()
  })

  it("suit une sous-route non listée jusqu'à son entrée", () => {
    expect(filParDefaut('/notes/42')).toEqual([{ label: 'Outils' }, { label: 'Journal' }])
  })
})

describe('Header — affichage du fil', () => {
  it('affiche le fil dérivé du rail', () => {
    renderHeader('/notes')
    expect(fil()).toHaveTextContent('Outils')
    expect(fil()).toHaveTextContent('Journal')
  })

  it("n'affiche rien sur une route absente du rail", () => {
    renderHeader('/route-inconnue')
    expect(fil()).toBeNull()
  })

  it("laisse une page surcharger le fil pour suivre son onglet", () => {
    const PageAOnglets = () => {
      useFilDAriane([{ label: 'Crowdfunding' }, { label: 'Performance' }])
      return null
    }
    renderHeader('/crowdfunding', PageAOnglets)
    expect(fil()).toHaveTextContent('Performance')
  })

  it('un seul fil dans le document', () => {
    renderHeader('/portfolio')
    expect(screen.getAllByRole('navigation', { name: /fil d'ariane/i })).toHaveLength(1)
  })
})
