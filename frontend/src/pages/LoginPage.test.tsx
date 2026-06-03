import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import LoginPage from './LoginPage'

// Mock useNavigate
const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

// Mock authStore
const mockLogin = vi.fn()
const mockClearError = vi.fn()
vi.mock('@/stores/authStore', () => ({
  useAuthStore: (selector?: (state: Record<string, unknown>) => unknown) => {
    const state = {
      login: mockLogin,
      isLoading: false,
      error: null,
      clearError: mockClearError,
    }
    if (selector) return selector(state)
    return state
  },
}))

// Mock toast
vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}))

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders login form', () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    )
    expect(screen.getByText('Bon retour')).toBeInTheDocument()
    expect(screen.getByLabelText('Adresse email')).toBeInTheDocument()
    expect(screen.getByLabelText('Mot de passe')).toBeInTheDocument()
    expect(screen.getByText('Se connecter')).toBeInTheDocument()
  })

  it('renders register link', () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    )
    expect(screen.getByText('Ouvrir un compte')).toBeInTheDocument()
  })

  it('renders the univers pills on the brand panel', () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    )
    expect(screen.getByText('Crypto')).toBeInTheDocument()
    expect(screen.getByText('Actions')).toBeInTheDocument()
    expect(screen.getByText('Crowdfunding')).toBeInTheDocument()
    expect(screen.getByText('Prédictions')).toBeInTheDocument()
  })

  it('calls login on form submit', async () => {
    mockLogin.mockResolvedValue(undefined)

    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    )

    fireEvent.change(screen.getByLabelText('Adresse email'), {
      target: { value: 'test@example.com' },
    })
    fireEvent.change(screen.getByLabelText('Mot de passe'), {
      target: { value: 'password123' },
    })
    fireEvent.click(screen.getByText('Se connecter'))

    await waitFor(() => {
      expect(mockClearError).toHaveBeenCalled()
      expect(mockLogin).toHaveBeenCalledWith('test@example.com', 'password123', undefined, false)
    })
  })

  it('shows forgot password link', () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    )
    expect(screen.getByText('Oublié ?')).toBeInTheDocument()
  })
})
