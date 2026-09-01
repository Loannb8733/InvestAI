import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest'
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

// Déclaré via vi.hoisted : vi.mock est remonté au-dessus des imports, une const
// ordinaire ne serait pas encore initialisée au moment où la factory s'exécute.
const getInvestorProfileMock = vi.hoisted(() =>
  vi.fn().mockResolvedValue({ tmi_rate: null, risk_profile: null, monthly_dca_eur: null })
)

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
    // Profil investisseur (TMI / risque / DCA) — carte ajoutée à SettingsPage
    getInvestorProfile: getInvestorProfileMock,
    updateInvestorProfile: vi.fn(),
  },
  investorProfileQueryKey: ['auth', 'investor-profile'],
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

describe('SettingsPage — profil investisseur indisponible (UX-04)', () => {
  /**
   * Pourquoi masquer le formulaire, et pas seulement afficher une alerte.
   *
   * `handleInvestorSave` envoie `null` pour tout champ vide. Quand la lecture du
   * profil échoue, les trois champs restent vides : un clic sur « Enregistrer »
   * effacerait TMI, profil de risque et DCA mensuel. La perte serait silencieuse
   * — l'utilisateur n'a aucun moyen de voir que les champs affichés ne sont pas
   * les siens.
   */
  beforeEach(() => {
    getInvestorProfileMock.mockReset()
  })

  afterEach(() => {
    getInvestorProfileMock.mockResolvedValue({ tmi_rate: null, risk_profile: null, monthly_dca_eur: null })
  })

  it('affiche un état d\'erreur quand le profil ne se charge pas', async () => {
    getInvestorProfileMock.mockRejectedValue(new Error('500'))
    renderWithProviders()
    expect(await screen.findByText('Profil investisseur indisponible')).toBeInTheDocument()
  })

  it('retire le bouton d\'enregistrement, pour ne pas écraser le profil par des vides', async () => {
    getInvestorProfileMock.mockRejectedValue(new Error('500'))
    renderWithProviders()
    await screen.findByText('Profil investisseur indisponible')
    expect(screen.queryByText('Enregistrer le profil investisseur')).not.toBeInTheDocument()
  })

  it('propose de réessayer', async () => {
    getInvestorProfileMock.mockRejectedValue(new Error('500'))
    renderWithProviders()
    expect(await screen.findByRole('button', { name: /réessayer/i })).toBeInTheDocument()
  })

  it('laisse le formulaire en place quand le chargement réussit', async () => {
    getInvestorProfileMock.mockResolvedValue({ tmi_rate: 0.3, risk_profile: null, monthly_dca_eur: null })
    renderWithProviders()
    expect(await screen.findByText('Enregistrer le profil investisseur')).toBeInTheDocument()
    expect(screen.queryByText('Profil investisseur indisponible')).not.toBeInTheDocument()
  })
})
