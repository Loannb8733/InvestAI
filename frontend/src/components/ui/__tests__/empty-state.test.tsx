import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import EmptyState from '@/components/ui/empty-state'
import { Button } from '@/components/ui/button'

describe('EmptyState', () => {
  it('variante empty : role="status", titre et description', () => {
    render(
      <EmptyState title="Aucune transaction" description="Importez un CSV pour commencer." />
    )
    const region = screen.getByRole('status')
    expect(region).toHaveTextContent('Aucune transaction')
    expect(region).toHaveTextContent('Importez un CSV pour commencer.')
  })

  it('variante error : role="alert"', () => {
    render(<EmptyState variant="error" title="Chargement impossible" />)
    expect(screen.getByRole('alert')).toHaveTextContent('Chargement impossible')
  })

  it('le slot action est cliquable', () => {
    const onRetry = vi.fn()
    render(
      <EmptyState
        variant="error"
        title="Erreur"
        action={<Button onClick={onRetry}>Réessayer</Button>}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: 'Réessayer' }))
    expect(onRetry).toHaveBeenCalledOnce()
  })
})
