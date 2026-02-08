import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import SettingsPage from './SettingsPage'

// Mock authStore
vi.mock('@/stores/authStore', () => ({
  useAuthStore: (selector?: (state: Record<string, unknown>) => unknown) => {
    const state = {
      user: {
        email: 'test@example.com',
        role: 'user',
        firstName: 'Jean',
        lastName: 'Dupont',
        mfaEnabled: false,
      },
      fetchCurrentUser: vi.fn(),
    }
    if (selector) return selector(state)
    return state
  },
}))

// Mock theme provider
vi.mock('@/components/theme-provider', () => ({
  useTheme: () => ({ theme: 'dark', setTheme: vi.fn() }),
}))

// Mock toast
vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}))

// Mock API
vi.mock('@/services/api', () => ({
  authApi: {
    setupMFA: vi.fn(),
    verifyMFA: vi.fn(),
    disableMFA: vi.fn(),
  },
  profileApi: {
    updateProfile: vi.fn(),
    changePassword: vi.fn(),
  },
}))

function renderWithProviders() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <SettingsPage />
    </QueryClientProvider>
  )
}

describe('SettingsPage', () => {
  it('renders page title', () => {
    renderWithProviders()
    expect(screen.getByText('Paramètres')).toBeInTheDocument()
  })

  it('renders profile section with user data', () => {
    renderWithProviders()
    expect(screen.getByText('Profil')).toBeInTheDocument()
    expect(screen.getByDisplayValue('test@example.com')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Jean')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Dupont')).toBeInTheDocument()
  })

  it('renders security section', () => {
    renderWithProviders()
    expect(screen.getByText('Sécurité')).toBeInTheDocument()
    expect(screen.getByText('Authentification à deux facteurs (MFA)')).toBeInTheDocument()
  })

  it('renders appearance section', () => {
    renderWithProviders()
    expect(screen.getByText('Apparence')).toBeInTheDocument()
    expect(screen.getByText('Clair')).toBeInTheDocument()
    expect(screen.getByText('Sombre')).toBeInTheDocument()
  })

  it('renders API keys section', () => {
    renderWithProviders()
    expect(screen.getByText('Clés API Exchanges')).toBeInTheDocument()
  })

  it('shows MFA activate button when MFA is disabled', () => {
    renderWithProviders()
    expect(screen.getByText('Activer')).toBeInTheDocument()
  })

  it('renders password change form', () => {
    renderWithProviders()
    expect(screen.getByLabelText('Mot de passe actuel')).toBeInTheDocument()
    expect(screen.getByLabelText('Nouveau mot de passe')).toBeInTheDocument()
    expect(screen.getByLabelText('Confirmer le mot de passe')).toBeInTheDocument()
    expect(screen.getByText('Changer le mot de passe')).toBeInTheDocument()
  })

  it('disables email field', () => {
    renderWithProviders()
    const emailInput = screen.getByDisplayValue('test@example.com')
    expect(emailInput).toBeDisabled()
  })
})
