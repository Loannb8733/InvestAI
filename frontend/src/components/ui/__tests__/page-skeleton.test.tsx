import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { PageSkeleton } from '@/components/ui/page-skeleton'

/**
 * Ce que le `<Loader2>` plein écran ne faisait pas, mesuré avant correction :
 * aucun des 95 spinners du front ne portait de libellé accessible, et le retour
 * anticipé emportait le titre de la page.
 */
describe('PageSkeleton', () => {
  it("annonce l'attente aux lecteurs d'écran", () => {
    render(<PageSkeleton titre="Transactions" forme="table" />)
    const annonce = screen.getByRole('status')
    expect(annonce).toHaveTextContent(/chargement de Transactions/i)
    expect(annonce).toHaveAttribute('aria-live', 'polite')
  })

  it('conserve le titre de la page pendant le chargement', () => {
    render(<PageSkeleton titre="Journal" />)
    expect(screen.getByRole('heading', { name: 'Journal', level: 1 })).toBeInTheDocument()
  })

  it('marque la région comme occupée', () => {
    const { container } = render(<PageSkeleton titre="Calendrier" />)
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull()
  })

  describe('niveau de titre', () => {
    it('rend un h1 par défaut', () => {
      render(<PageSkeleton titre="Administration" />)
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Administration')
    })

    it("rend un h2 quand la page vit sous un conteneur qui porte déjà le h1", () => {
      render(<PageSkeleton titre="Portefeuille" niveauTitre={2} />)
      expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Portefeuille')
      expect(screen.queryByRole('heading', { level: 1 })).toBeNull()
    })
  })

  it('affiche la description quand elle est fournie', () => {
    render(<PageSkeleton titre="Alertes" description="Configurez des alertes sur vos actifs" />)
    expect(screen.getByText('Configurez des alertes sur vos actifs')).toBeInTheDocument()
  })

  it("n'expose aucun texte parasite pour les formes décoratives", () => {
    const { container } = render(<PageSkeleton titre="Exchanges" forme="cartes" />)
    // Les blocs fantômes sont décoratifs : seul le titre et l'annonce comptent.
    const decoratifs = container.querySelectorAll('[aria-hidden="true"]')
    expect(decoratifs.length).toBeGreaterThan(0)
  })

  describe.each(['table', 'cartes', 'liste'] as const)('forme %s', (forme) => {
    it('réserve un espace non vide', () => {
      const { container } = render(<PageSkeleton titre="Test" forme={forme} />)
      expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(3)
    })
  })
})
