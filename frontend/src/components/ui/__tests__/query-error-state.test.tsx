import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import QueryErrorState from '../query-error-state'

/**
 * UX-04 — une `useQuery` en échec ne rendait rien.
 *
 * Le `RouteErrorBoundary` ne rattrape pas une query rejetée : elle ne lève aucune
 * exception pendant le rendu. La page restait donc vide ou tournait indéfiniment,
 * sans que l'utilisateur puisse distinguer « aucune donnée » de « l'API est tombée »,
 * ni relancer la requête. 26 pages sur 32 étaient dans ce cas.
 */

describe('QueryErrorState', () => {
  it('annonce l’erreur aux lecteurs d’écran', () => {
    render(<QueryErrorState />)
    // role="alert" : l'échec est interruptif, contrairement à un état vide.
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('affiche un titre lisible par défaut', () => {
    render(<QueryErrorState />)
    expect(screen.getByText(/impossible de charger/i)).toBeInTheDocument()
  })

  it('accepte un titre spécifique à la page', () => {
    render(<QueryErrorState title="Impossible de charger le calendrier" />)
    expect(screen.getByText('Impossible de charger le calendrier')).toBeInTheDocument()
  })

  it('propose de réessayer et appelle refetch', () => {
    const onRetry = vi.fn()
    render(<QueryErrorState onRetry={onRetry} />)
    fireEvent.click(screen.getByRole('button', { name: /réessayer/i }))
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('n’affiche aucun bouton sans moyen de réessayer', () => {
    // Proposer une action qui ne fait rien est pire que ne rien proposer.
    render(<QueryErrorState />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('désactive le bouton pendant la nouvelle tentative', () => {
    render(<QueryErrorState onRetry={() => {}} busy />)
    expect(screen.getByRole('button')).toBeDisabled()
    expect(screen.getByText(/nouvelle tentative/i)).toBeInTheDocument()
  })

  it('reste lisible quand l’erreur n’est pas une Error', () => {
    render(<QueryErrorState error={{ statut: 500 }} />)
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('accepte une description propre à la page', () => {
    render(<QueryErrorState description="Le service de cotation ne répond pas." />)
    expect(screen.getByText('Le service de cotation ne répond pas.')).toBeInTheDocument()
  })
})
