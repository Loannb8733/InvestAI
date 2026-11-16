import { beforeAll, beforeEach, describe, it, expect, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { http } from '@/shared/api/http'
import { createFakeServer, ok } from '@/test/fakeServer'
import { PROFILE, resetAuth, SIGNED_IN_USER } from '@/test/identityFixtures'
import { renderWithQuery } from '@/test/render'
import SettingsPage from './SettingsPage'

vi.mock('@/components/theme-provider', () => ({
  useTheme: () => ({ theme: 'dark', setTheme: vi.fn() }),
}))

vi.mock('@/hooks/use-toast', () => ({ toast: vi.fn(), useToast: () => ({ toast: vi.fn() }) }))

const server = createFakeServer()
const profile = (investor: Record<string, unknown>) => ok({ ...PROFILE, ...investor })

beforeAll(() => {
  http.defaults.adapter = server.adapter
})

beforeEach(() => {
  server.reset({ 'GET /auth/me': profile({ tmi_rate: null, risk_profile: null, monthly_dca_eur: null }) })
  resetAuth({
    isAuthenticated: true,
    accessToken: 'access-1',
    user: { ...SIGNED_IN_USER, email: 'test@example.com', firstName: 'Jean', lastName: 'Dupont' },
  })
})

function renderWithProviders() {
  return renderWithQuery(<SettingsPage />)
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
  it('affiche un état d\'erreur quand le profil ne se charge pas', async () => {
    server.routes['GET /auth/me'] = () => ({ status: 500, data: { detail: 'boom' } })
    renderWithProviders()
    expect(await screen.findByText('Profil investisseur indisponible')).toBeInTheDocument()
  })

  it('retire le bouton d\'enregistrement, pour ne pas écraser le profil par des vides', async () => {
    server.routes['GET /auth/me'] = () => ({ status: 500, data: { detail: 'boom' } })
    renderWithProviders()
    await screen.findByText('Profil investisseur indisponible')
    expect(screen.queryByText('Enregistrer le profil investisseur')).not.toBeInTheDocument()
  })

  it('propose de réessayer', async () => {
    server.routes['GET /auth/me'] = () => ({ status: 500, data: { detail: 'boom' } })
    renderWithProviders()
    // Le titre d'abord : `findByRole` relancerait à chaque sondage une requête
    // quarante fois plus coûteuse que `findByText` sur cette page.
    await screen.findByText('Profil investisseur indisponible')
    expect(screen.getByRole('button', { name: /réessayer/i })).toBeInTheDocument()
  })

  it('laisse le formulaire en place quand le chargement réussit', async () => {
    server.routes['GET /auth/me'] = profile({ tmi_rate: 0.3, risk_profile: null, monthly_dca_eur: null })
    renderWithProviders()
    expect(await screen.findByText('Enregistrer le profil investisseur')).toBeInTheDocument()
    expect(screen.queryByText('Profil investisseur indisponible')).not.toBeInTheDocument()
  })
})
