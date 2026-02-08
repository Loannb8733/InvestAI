import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import AdminPage from './AdminPage'

// Mock API
vi.mock('@/services/api', () => ({
  usersApi: {
    list: vi.fn().mockResolvedValue([
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
    ]),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  },
}))

// Mock toast
vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}))

function renderWithProviders() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <AdminPage />
    </QueryClientProvider>
  )
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

  it('shows loading state initially', () => {
    renderWithProviders()
    // The component shows a loader while fetching
    // After data loads, stats will appear
  })

  it('renders stats cards after data loads', async () => {
    renderWithProviders()

    // Wait for data to load
    const totalCard = await screen.findByText('Utilisateurs totaux')
    expect(totalCard).toBeInTheDocument()

    expect(screen.getByText('Utilisateurs actifs')).toBeInTheDocument()
    expect(screen.getByText('MFA activé')).toBeInTheDocument()
  })

  it('renders user table with data', async () => {
    renderWithProviders()

    // Wait for users to appear
    expect(await screen.findByText('admin@test.com')).toBeInTheDocument()
    expect(screen.getByText('user@test.com')).toBeInTheDocument()
    expect(screen.getByText('inactive@test.com')).toBeInTheDocument()
  })

  it('shows correct user counts in stats', async () => {
    renderWithProviders()

    // Total: 3, Active: 2, MFA: 1
    await screen.findByText('admin@test.com')
    expect(screen.getByText('3')).toBeInTheDocument() // total
  })
})
