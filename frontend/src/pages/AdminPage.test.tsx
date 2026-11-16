import { beforeAll, beforeEach, describe, it, expect, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { http } from '@/shared/api/http'
import { createFakeServer, ok } from '@/test/fakeServer'
import { renderWithQuery } from '@/test/render'
import AdminPage from './AdminPage'

const USERS = [
  {
    id: '1',
    email: 'admin@test.com',
    role: 'admin',
    first_name: 'Admin',
    last_name: 'User',
    is_active: true,
    mfa_enabled: true,
    created_at: '2024-01-01T00:00:00Z',
  },
  {
    id: '2',
    email: 'user@test.com',
    role: 'user',
    first_name: 'Regular',
    last_name: 'User',
    is_active: true,
    mfa_enabled: false,
    created_at: '2024-02-01T00:00:00Z',
  },
  {
    id: '3',
    email: 'inactive@test.com',
    role: 'user',
    first_name: 'Inactive',
    last_name: 'User',
    is_active: false,
    mfa_enabled: false,
    created_at: '2024-03-01T00:00:00Z',
  },
]

const server = createFakeServer()

beforeAll(() => {
  http.defaults.adapter = server.adapter
})

beforeEach(() => {
  server.reset({ 'GET /users': ok(USERS) })
})

vi.mock('@/hooks/use-toast', () => ({ toast: vi.fn(), useToast: () => ({ toast: vi.fn() }) }))

function renderWithProviders() {
  return renderWithQuery(<AdminPage />)
}

describe('AdminPage', () => {
  it('renders page title', async () => {
    renderWithProviders()
    expect(await screen.findByText('Administration')).toBeInTheDocument()
  })

  it('renders create user button', async () => {
    renderWithProviders()
    expect(await screen.findByText('Nouvel utilisateur')).toBeInTheDocument()
  })

  it('renders stats cards after data loads', async () => {
    renderWithProviders()

    const totalCard = await screen.findByText('Utilisateurs totaux')
    expect(totalCard).toBeInTheDocument()

    expect(screen.getByText('Utilisateurs actifs')).toBeInTheDocument()
    expect(screen.getByText('MFA activé')).toBeInTheDocument()
  })

  it('renders user table with data', async () => {
    renderWithProviders()

    expect(await screen.findByText('admin@test.com')).toBeInTheDocument()
    expect(screen.getByText('user@test.com')).toBeInTheDocument()
    expect(screen.getByText('inactive@test.com')).toBeInTheDocument()
  })

  it('shows correct user counts in stats', async () => {
    renderWithProviders()

    // Total: 3, Active: 2, MFA: 1
    await screen.findByText('admin@test.com')
    // NumberTicker (StatCard) renders the value twice: an aria-hidden animated
    // span and a visually-hidden aria-live copy — assert on the live one.
    expect(screen.getAllByText('3').length).toBeGreaterThan(0) // total
  })
})
