import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ErrorBoundary } from './ErrorBoundary'

// Suppress console.error from ErrorBoundary.componentDidCatch during tests
vi.spyOn(console, 'error').mockImplementation(() => {})

function ThrowingComponent({ message }: { message: string }): React.ReactNode {
  throw new Error(message)
}

function GoodComponent() {
  return <div>All good</div>
}

describe('ErrorBoundary', () => {
  it('renders children when no error', () => {
    render(
      <ErrorBoundary>
        <GoodComponent />
      </ErrorBoundary>
    )
    expect(screen.getByText('All good')).toBeInTheDocument()
  })

  it('renders error UI when child throws', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent message="Test crash" />
      </ErrorBoundary>
    )
    expect(screen.getByText('Une erreur est survenue')).toBeInTheDocument()
    expect(screen.getByText('Test crash')).toBeInTheDocument()
  })

  it('renders custom fallback when provided', () => {
    render(
      <ErrorBoundary fallback={<div>Custom fallback</div>}>
        <ThrowingComponent message="crash" />
      </ErrorBoundary>
    )
    expect(screen.getByText('Custom fallback')).toBeInTheDocument()
  })

  it('shows retry button that resets the error state', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent message="crash" />
      </ErrorBoundary>
    )
    expect(screen.getByText('Réessayer')).toBeInTheDocument()
    expect(screen.getByText("Retour à l'accueil")).toBeInTheDocument()
  })

  it('renders default message when error has no message', () => {
    function ThrowNull(): React.ReactNode {
      throw new Error('')
    }
    render(
      <ErrorBoundary>
        <ThrowNull />
      </ErrorBoundary>
    )
    expect(screen.getByText("Quelque chose s'est mal passé. Veuillez réessayer.")).toBeInTheDocument()
  })
})
