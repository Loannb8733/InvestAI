import { useAuthStore } from '@/stores/authStore'
import { ok, type Handler } from './fakeServer'

export const TOKENS = { access_token: 'access-1', refresh_token: 'refresh-1', token_type: 'bearer' }

export const PROFILE = {
  id: 'u1',
  email: 'jeanne@example.com',
  role: 'user',
  first_name: 'Jeanne',
  last_name: 'Martin',
  preferred_currency: 'EUR',
  mfa_enabled: false,
  telegram_chat_id: null,
  telegram_enabled: false,
  tmi_rate: 0.3,
  risk_profile: 'moderate',
  monthly_dca_eur: 250,
  created_at: '2026-01-10T08:00:00Z',
}

export const USERS = [
  {
    id: 'u1',
    email: 'jeanne@example.com',
    first_name: 'Jeanne',
    last_name: 'Martin',
    role: 'admin',
    is_active: true,
    mfa_enabled: true,
    created_at: '2026-01-10T08:00:00Z',
    updated_at: '2026-01-10T08:00:00Z',
  },
  {
    id: 'u2',
    email: 'paul@example.com',
    first_name: null,
    last_name: null,
    role: 'user',
    is_active: false,
    mfa_enabled: false,
    created_at: '2026-02-20T16:30:00Z',
    updated_at: '2026-02-20T16:30:00Z',
  },
]

const message = (text: string): Handler => ok({ message: text })

export function identityRoutes(): Record<string, Handler> {
  return {
    'POST /auth/login': ok(TOKENS),
    'POST /auth/refresh': ok({ ...TOKENS, access_token: 'access-2', refresh_token: 'refresh-2' }),
    'POST /auth/logout': message('Déconnexion réussie'),
    'GET /auth/me': ok(PROFILE),
    'PATCH /auth/me': (config) => ({ status: 200, data: { ...PROFILE, ...JSON.parse(String(config.data)) } }),
    'POST /auth/register': message('Inscription enregistrée. Connectez-vous avec cette adresse.'),
    'POST /auth/forgot-password': message('Si un compte existe, un email a été envoyé.'),
    'POST /auth/reset-password': message('Mot de passe réinitialisé.'),
    'POST /auth/change-password': message('Mot de passe modifié.'),
    'POST /auth/mfa/setup': ok({ secret: 'JBSWY3DPEHPK3PXP', qr_code: 'data:image/png;base64,QR', backup_codes: ['AAAA-1111', 'BBBB-2222'] }),
    'POST /auth/mfa/verify': message('MFA activée'),
    'POST /auth/mfa/disable': message('MFA désactivée'),
    'GET /users': ok(USERS),
    'POST /users': (config) => ({ status: 201, data: { ...USERS[1], id: 'u9', ...JSON.parse(String(config.data)) } }),
    'PATCH /users/u2': (config) => ({ status: 200, data: { ...USERS[1], ...JSON.parse(String(config.data)) } }),
    'DELETE /users/u2': () => ({ status: 204 }),
  }
}

export function resetAuth(signedIn: Partial<ReturnType<typeof useAuthStore.getState>> = {}) {
  localStorage.clear()
  useAuthStore.setState({
    user: null,
    accessToken: null,
    refreshToken: null,
    isAuthenticated: false,
    isLoading: false,
    isHydrating: false,
    error: null,
    ...signedIn,
  })
}

export const SIGNED_IN_USER = {
  id: 'u1',
  email: 'jeanne@example.com',
  role: 'user' as const,
  firstName: 'Jeanne',
  lastName: 'Martin',
  preferredCurrency: 'EUR',
  mfaEnabled: false,
  telegramEnabled: false,
}

export function authSnapshot() {
  const { user, accessToken, refreshToken, isAuthenticated, error } = useAuthStore.getState()
  return { user, accessToken, refreshToken, isAuthenticated, error }
}
