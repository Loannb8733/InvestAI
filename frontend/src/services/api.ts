import axios, { AxiosError } from 'axios'
import { useAuthStore } from '@/stores/authStore'

const API_URL = import.meta.env.VITE_API_URL || '/api/v1'

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor to add auth token
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Track if we're currently refreshing to prevent infinite loops
let isRefreshing = false
let failedQueue: Array<{
  resolve: (token: string) => void
  reject: (error: unknown) => void
}> = []

const processQueue = (error: unknown, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error)
    } else if (token) {
      prom.resolve(token)
    }
  })
  failedQueue = []
}

// Response interceptor to handle token refresh
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as typeof error.config & { _retry?: boolean }

    // Don't retry refresh token requests or already retried requests
    if (
      error.response?.status === 401 &&
      originalRequest &&
      !originalRequest._retry &&
      !originalRequest.url?.includes('/auth/refresh')
    ) {
      if (isRefreshing) {
        // Wait for the refresh to complete
        return new Promise((resolve, reject) => {
          failedQueue.push({
            resolve: (token: string) => {
              originalRequest.headers.Authorization = `Bearer ${token}`
              resolve(api(originalRequest))
            },
            reject: (err: unknown) => {
              reject(err)
            },
          })
        })
      }

      originalRequest._retry = true
      isRefreshing = true

      try {
        await useAuthStore.getState().refreshAccessToken()
        const token = useAuthStore.getState().accessToken

        if (token) {
          processQueue(null, token)
          originalRequest.headers.Authorization = `Bearer ${token}`
          return api(originalRequest)
        } else {
          processQueue(new Error('No token after refresh'), null)
          useAuthStore.getState().logout()
        }
      } catch (refreshError) {
        processQueue(refreshError, null)
        useAuthStore.getState().logout()
        return Promise.reject(refreshError)
      } finally {
        isRefreshing = false
      }
    }

    return Promise.reject(error)
  }
)

// Auth API
export const authApi = {
  register: async (email: string, password: string, firstName?: string, lastName?: string) => {
    const response = await api.post('/auth/register', {
      email,
      password,
      first_name: firstName,
      last_name: lastName,
    })
    return response.data
  },

  login: async (email: string, password: string, mfaCode?: string) => {
    const response = await api.post('/auth/login', { email, password, mfa_code: mfaCode })
    return response.data
  },

  refresh: async (refreshToken: string) => {
    const response = await api.post('/auth/refresh', { refresh_token: refreshToken })
    return response.data
  },

  getCurrentUser: async () => {
    const response = await api.get('/auth/me')
    return response.data
  },

  setupMFA: async () => {
    const response = await api.post('/auth/mfa/setup')
    return response.data
  },

  verifyMFA: async (code: string) => {
    const response = await api.post('/auth/mfa/verify', { code })
    return response.data
  },

  disableMFA: async (code: string) => {
    const response = await api.post('/auth/mfa/disable', { code })
    return response.data
  },

  verifyEmail: async (token: string) => {
    const response = await api.post('/auth/verify-email', { token })
    return response.data
  },

  resendVerification: async (email: string) => {
    const response = await api.post('/auth/resend-verification', { email })
    return response.data
  },
}

// Dashboard API
export const dashboardApi = {
  getMetrics: async (days: number = 30) => {
    const response = await api.get('/dashboard', { params: { days } })
    return response.data
  },

  getPortfolioMetrics: async (portfolioId: string) => {
    const response = await api.get(`/dashboard/portfolio/${portfolioId}`)
    return response.data
  },

  getPortfolioHistory: async (portfolioId: string) => {
    const response = await api.get(`/dashboard/portfolio/${portfolioId}/history`)
    return response.data
  },

  getHistoricalData: async (days: number = 30) => {
    const response = await api.get('/dashboard/historical-data', { params: { days } })
    return response.data
  },

  getRecentTransactions: async (limit: number = 10) => {
    const response = await api.get('/dashboard/recent-transactions', { params: { limit } })
    return response.data
  },

  getActiveAlerts: async () => {
    const response = await api.get('/dashboard/active-alerts')
    return response.data
  },

  getUpcomingEvents: async (days: number = 30) => {
    const response = await api.get('/dashboard/upcoming-events', { params: { days } })
    return response.data
  },

  getBenchmarks: async (days: number = 90) => {
    const response = await api.get('/dashboard/benchmarks', { params: { days } })
    return response.data
  },
}

// Portfolios API
export const portfoliosApi = {
  list: async () => {
    const response = await api.get('/portfolios')
    return response.data
  },

  create: async (data: { name: string; description?: string }) => {
    const response = await api.post('/portfolios', data)
    return response.data
  },

  get: async (id: string) => {
    const response = await api.get(`/portfolios/${id}`)
    return response.data
  },

  update: async (id: string, data: { name?: string; description?: string }) => {
    const response = await api.patch(`/portfolios/${id}`, data)
    return response.data
  },

  delete: async (id: string) => {
    await api.delete(`/portfolios/${id}`)
  },

  updateCashBalance: async (id: string, exchange: string, amount: number) => {
    const response = await api.put(`/portfolios/${id}/cash-balance`, { exchange, amount })
    return response.data
  },

  deleteCashBalance: async (id: string, exchange: string) => {
    const response = await api.delete(`/portfolios/${id}/cash-balance/${encodeURIComponent(exchange)}`)
    return response.data
  },
}

// Assets API
export const assetsApi = {
  list: async (portfolioId?: string) => {
    const params = portfolioId ? { portfolio_id: portfolioId } : {}
    const response = await api.get('/assets', { params })
    return response.data
  },

  create: async (data: {
    portfolio_id: string
    symbol: string
    name?: string
    asset_type: string
    quantity?: number
    avg_buy_price?: number
    currency?: string
    exchange?: string
  }) => {
    const response = await api.post('/assets', data)
    return response.data
  },

  get: async (id: string) => {
    const response = await api.get(`/assets/${id}`)
    return response.data
  },

  update: async (id: string, data: {
    name?: string
    quantity?: number
    avg_buy_price?: number
  }) => {
    const response = await api.patch(`/assets/${id}`, data)
    return response.data
  },

  delete: async (id: string) => {
    await api.delete(`/assets/${id}`)
  },
}

// Transactions API
export const transactionsApi = {
  list: async (params?: { asset_id?: string; portfolio_id?: string; skip?: number; limit?: number }) => {
    const response = await api.get('/transactions', { params })
    return response.data
  },

  create: async (data: {
    asset_id: string
    transaction_type: string
    quantity: number
    price: number
    fee?: number
    currency?: string
    executed_at?: string
    notes?: string
  }) => {
    const response = await api.post('/transactions', data)
    return response.data
  },

  get: async (id: string) => {
    const response = await api.get(`/transactions/${id}`)
    return response.data
  },

  delete: async (id: string) => {
    await api.delete(`/transactions/${id}`)
  },

  update: async (id: string, data: {
    transaction_type?: string
    quantity?: number
    price?: number
    fee?: number
    fee_currency?: string
    currency?: string
    executed_at?: string
    exchange?: string
    notes?: string
  }) => {
    const response = await api.patch(`/transactions/${id}`, data)
    return response.data
  },

  deleteAll: async () => {
    const response = await api.delete('/transactions/all')
    return response.data
  },

  importCSV: async (file: File, portfolioId?: string, platform?: string) => {
    const formData = new FormData()
    formData.append('file', file)
    const params: Record<string, string> = {}
    if (portfolioId) {
      params.portfolio_id = portfolioId
    }
    if (platform) {
      params.platform = platform
    }
    const response = await api.post('/transactions/import-csv', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      params,
    })
    return response.data
  },

  getCSVPlatforms: async () => {
    const response = await api.get('/transactions/csv-platforms')
    return response.data
  },

  exportCSV: async (portfolioId?: string) => {
    const params = portfolioId ? { portfolio_id: portfolioId } : {}
    const response = await api.get('/transactions/export-csv', {
      params,
      responseType: 'blob',
    })
    return response.data
  },
}

// Analytics API
const ANALYTICS_TIMEOUT = 120000 // 2 minutes — historical data fetches are slow

export const analyticsApi = {
  getGlobal: async (days?: number) => {
    const response = await api.get('/analytics', { params: days ? { days } : {}, timeout: ANALYTICS_TIMEOUT })
    return response.data
  },

  getPortfolio: async (portfolioId: string, days?: number) => {
    const response = await api.get(`/analytics/portfolio/${portfolioId}`, { params: days ? { days } : {}, timeout: ANALYTICS_TIMEOUT })
    return response.data
  },

  getCorrelation: async (portfolioId?: string, days?: number) => {
    const response = await api.get('/analytics/correlation', {
      params: { ...(portfolioId ? { portfolio_id: portfolioId } : {}), ...(days ? { days } : {}) },
      timeout: ANALYTICS_TIMEOUT,
    })
    return response.data
  },

  getDiversification: async (portfolioId?: string, days?: number) => {
    const response = await api.get('/analytics/diversification', {
      params: { ...(portfolioId ? { portfolio_id: portfolioId } : {}), ...(days ? { days } : {}) },
      timeout: ANALYTICS_TIMEOUT,
    })
    return response.data
  },

  getPerformance: async (period: string = '30d') => {
    const response = await api.get('/analytics/performance', { params: { period }, timeout: ANALYTICS_TIMEOUT })
    return response.data
  },

  getRiskMetrics: async () => {
    const response = await api.get('/analytics/risk-metrics', { timeout: ANALYTICS_TIMEOUT })
    return response.data
  },

  getMonteCarlo: async (horizon: number = 90) => {
    const response = await api.get('/analytics/monte-carlo', { params: { horizon }, timeout: ANALYTICS_TIMEOUT })
    return response.data
  },

  getXirr: async () => {
    const response = await api.get('/analytics/xirr', { timeout: ANALYTICS_TIMEOUT })
    return response.data
  },

  getOptimize: async (objective: string = 'max_sharpe') => {
    const response = await api.get('/analytics/optimize', { params: { objective }, timeout: ANALYTICS_TIMEOUT })
    return response.data
  },

  getStressTest: async () => {
    const response = await api.get('/analytics/stress-test', { timeout: ANALYTICS_TIMEOUT })
    return response.data
  },

  getBeta: async (days: number = 90) => {
    const response = await api.get('/analytics/beta', { params: { days }, timeout: ANALYTICS_TIMEOUT })
    return response.data
  },

  postRebalance: async (targetWeights: Record<string, number>) => {
    const response = await api.post('/analytics/rebalance', targetWeights, { timeout: ANALYTICS_TIMEOUT })
    return response.data
  },
}

// Insights API
export const insightsApi = {
  getFees: async () => {
    const response = await api.get('/insights/fees', { timeout: ANALYTICS_TIMEOUT })
    return response.data
  },

  getTaxLossHarvesting: async () => {
    const response = await api.get('/insights/tax-loss-harvesting', { timeout: ANALYTICS_TIMEOUT })
    return response.data
  },

  getPassiveIncome: async (year?: number) => {
    const response = await api.get('/insights/passive-income', { params: year ? { year } : {}, timeout: ANALYTICS_TIMEOUT })
    return response.data
  },

  backtestDca: async (symbol: string, assetType: string, monthlyAmount: number, startYear: number, startMonth: number = 1) => {
    const response = await api.get('/insights/backtest-dca', {
      params: { symbol, asset_type: assetType, monthly_amount: monthlyAmount, start_year: startYear, start_month: startMonth },
      timeout: ANALYTICS_TIMEOUT,
    })
    return response.data
  },
}

// API Keys API
export const apiKeysApi = {
  listExchanges: async () => {
    const response = await api.get('/api-keys/exchanges')
    return response.data
  },

  list: async () => {
    const response = await api.get('/api-keys')
    return response.data
  },

  create: async (data: {
    exchange: string
    label?: string
    api_key: string
    secret_key?: string
    passphrase?: string
  }) => {
    const response = await api.post('/api-keys', data)
    return response.data
  },

  update: async (id: string, data: {
    label?: string
    api_key?: string
    secret_key?: string
    passphrase?: string
    is_active?: boolean
  }) => {
    const response = await api.patch(`/api-keys/${id}`, data)
    return response.data
  },

  delete: async (id: string) => {
    await api.delete(`/api-keys/${id}`)
  },

  test: async (id: string) => {
    const response = await api.post(`/api-keys/${id}/test`)
    return response.data
  },

  sync: async (id: string) => {
    const response = await api.post(`/api-keys/${id}/sync`)
    return response.data
  },

  importHistory: async (id: string) => {
    const response = await api.post(`/api-keys/${id}/import-history`, {}, {
      timeout: 300000, // 5 minutes timeout for import
    })
    return response.data
  },
}

// Predictions API
export const predictionsApi = {
  getAssetPrediction: async (symbol: string, assetType: string = 'crypto', days: number = 7) => {
    const response = await api.get(`/predictions/asset/${symbol}`, {
      params: { asset_type: assetType, days },
    })
    return response.data
  },

  getPortfolioPredictions: async (days: number = 7) => {
    const response = await api.get('/predictions/portfolio', { params: { days } })
    return response.data
  },

  getAnomalies: async () => {
    const response = await api.get('/predictions/anomalies')
    return response.data
  },

  getMarketSentiment: async () => {
    const response = await api.get('/predictions/sentiment')
    return response.data
  },

  whatIf: async (scenarios: Array<{ symbol: string; change_percent: number }>) => {
    const response = await api.post('/predictions/what-if', { scenarios })
    return response.data
  },

  getMarketEvents: async () => {
    const response = await api.get('/predictions/events')
    return response.data
  },
}

// Alerts API
export const alertsApi = {
  listConditions: async () => {
    const response = await api.get('/alerts/conditions')
    return response.data
  },

  getSummary: async () => {
    const response = await api.get('/alerts/summary')
    return response.data
  },

  list: async (activeOnly: boolean = false) => {
    const response = await api.get('/alerts', { params: { active_only: activeOnly } })
    return response.data
  },

  create: async (data: {
    asset_id: string
    name: string
    condition: string
    threshold: number
    currency?: string
    notify_email?: boolean
    notify_in_app?: boolean
  }) => {
    const response = await api.post('/alerts', data)
    return response.data
  },

  get: async (id: string) => {
    const response = await api.get(`/alerts/${id}`)
    return response.data
  },

  update: async (id: string, data: {
    name?: string
    threshold?: number
    is_active?: boolean
    notify_email?: boolean
    notify_in_app?: boolean
  }) => {
    const response = await api.patch(`/alerts/${id}`, data)
    return response.data
  },

  delete: async (id: string) => {
    await api.delete(`/alerts/${id}`)
  },

  checkAlerts: async () => {
    const response = await api.post('/alerts/check')
    return response.data
  },
}

// Reports API
export const reportsApi = {
  getAvailableYears: async () => {
    const response = await api.get('/reports/available-years')
    return response.data
  },

  downloadPerformancePDF: async () => {
    const response = await api.get('/reports/performance/pdf', {
      responseType: 'blob',
    })
    return response.data
  },

  downloadPerformanceExcel: async () => {
    const response = await api.get('/reports/performance/excel', {
      responseType: 'blob',
    })
    return response.data
  },

  downloadTaxPDF: async (year: number) => {
    const response = await api.get(`/reports/tax/${year}/pdf`, {
      responseType: 'blob',
    })
    return response.data
  },

  downloadTaxExcel: async (year: number) => {
    const response = await api.get(`/reports/tax/${year}/excel`, {
      responseType: 'blob',
    })
    return response.data
  },

  downloadTransactionsPDF: async (year?: number) => {
    const params = year ? { year } : {}
    const response = await api.get('/reports/transactions/pdf', {
      params,
      responseType: 'blob',
    })
    return response.data
  },
}

// Users API (admin only)
export const usersApi = {
  list: async () => {
    const response = await api.get('/users')
    return response.data
  },

  create: async (data: {
    email: string
    password: string
    role?: string
    first_name?: string
    last_name?: string
  }) => {
    const response = await api.post('/users', data)
    return response.data
  },

  get: async (id: string) => {
    const response = await api.get(`/users/${id}`)
    return response.data
  },

  update: async (id: string, data: {
    email?: string
    password?: string
    first_name?: string
    last_name?: string
    is_active?: boolean
  }) => {
    const response = await api.patch(`/users/${id}`, data)
    return response.data
  },

  delete: async (id: string) => {
    await api.delete(`/users/${id}`)
  },
}

// Notes API
export const notesApi = {
  getSummary: async () => {
    const response = await api.get('/notes/summary')
    return response.data
  },

  getTags: async () => {
    const response = await api.get('/notes/tags')
    return response.data
  },

  list: async (params?: { tag?: string; asset_id?: string; search?: string }) => {
    const response = await api.get('/notes', { params })
    return response.data
  },

  create: async (data: {
    title: string
    content?: string
    tags?: string
    asset_id?: string
  }) => {
    const response = await api.post('/notes', data)
    return response.data
  },

  get: async (id: string) => {
    const response = await api.get(`/notes/${id}`)
    return response.data
  },

  update: async (id: string, data: {
    title?: string
    content?: string
    tags?: string
    asset_id?: string
  }) => {
    const response = await api.patch(`/notes/${id}`, data)
    return response.data
  },

  delete: async (id: string) => {
    await api.delete(`/notes/${id}`)
  },
}

// Calendar API
export const calendarApi = {
  getEventTypes: async () => {
    const response = await api.get('/calendar/event-types')
    return response.data
  },

  getSummary: async () => {
    const response = await api.get('/calendar/summary')
    return response.data
  },

  getUpcoming: async (days: number = 30) => {
    const response = await api.get('/calendar/upcoming', { params: { days } })
    return response.data
  },

  list: async (params?: {
    start_date?: string
    end_date?: string
    event_type?: string
    show_completed?: boolean
  }) => {
    const response = await api.get('/calendar', { params })
    return response.data
  },

  create: async (data: {
    title: string
    description?: string
    event_type: string
    event_date: string
    is_recurring?: boolean
    recurrence_rule?: string
    amount?: number
    currency?: string
  }) => {
    const response = await api.post('/calendar', data)
    return response.data
  },

  get: async (id: string) => {
    const response = await api.get(`/calendar/${id}`)
    return response.data
  },

  update: async (id: string, data: {
    title?: string
    description?: string
    event_type?: string
    event_date?: string
    is_recurring?: boolean
    recurrence_rule?: string
    amount?: number
    currency?: string
    is_completed?: boolean
  }) => {
    const response = await api.patch(`/calendar/${id}`, data)
    return response.data
  },

  complete: async (id: string) => {
    const response = await api.post(`/calendar/${id}/complete`)
    return response.data
  },

  delete: async (id: string) => {
    await api.delete(`/calendar/${id}`)
  },
}

// Simulations API
export const simulationsApi = {
  getTypes: async () => {
    const response = await api.get('/simulations/types')
    return response.data
  },

  calculateFIRE: async (data: {
    current_portfolio_value: number
    monthly_contribution: number
    monthly_expenses: number
    expected_annual_return?: number
    inflation_rate?: number
    withdrawal_rate?: number
    target_years?: number
  }) => {
    const response = await api.post('/simulations/fire', data)
    return response.data
  },

  projectPortfolio: async (data: {
    years?: number
    expected_return?: number
    monthly_contribution?: number
    inflation_adjustment?: boolean
    inflation_rate?: number
  }) => {
    const response = await api.post('/simulations/projection', data)
    return response.data
  },

  simulateDCA: async (data: {
    total_amount: number
    frequency?: string
    duration_months?: number
    expected_volatility?: number
    expected_return?: number
  }) => {
    const response = await api.post('/simulations/dca', data)
    return response.data
  },

  simulateWhatIf: async (data: {
    scenario_type: string
    asset_changes?: Record<string, number>
    withdrawal_amount?: number
    contribution_amount?: number
  }) => {
    const response = await api.post('/simulations/what-if', data)
    return response.data
  },

  list: async (simulation_type?: string) => {
    const params = simulation_type ? { simulation_type } : {}
    const response = await api.get('/simulations', { params })
    return response.data
  },

  save: async (data: {
    name: string
    description?: string
    simulation_type: string
    parameters: Record<string, unknown>
  }) => {
    const response = await api.post('/simulations', data)
    return response.data
  },

  get: async (id: string) => {
    const response = await api.get(`/simulations/${id}`)
    return response.data
  },

  delete: async (id: string) => {
    await api.delete(`/simulations/${id}`)
  },
}

// Notifications API
export const notificationsApi = {
  list: async (unreadOnly: boolean = false, limit: number = 50) => {
    const response = await api.get('/notifications', { params: { unread_only: unreadOnly, limit } })
    return response.data
  },

  getUnreadCount: async () => {
    const response = await api.get('/notifications/count')
    return response.data
  },

  markAsRead: async (id: string) => {
    const response = await api.post(`/notifications/${id}/read`)
    return response.data
  },

  markAllAsRead: async () => {
    const response = await api.post('/notifications/read-all')
    return response.data
  },
}

// Profile API (user self-service)
export const profileApi = {
  updateProfile: async (data: { first_name?: string; last_name?: string; preferred_currency?: string }) => {
    const response = await api.patch('/auth/me', data)
    return response.data
  },

  changePassword: async (currentPassword: string, newPassword: string) => {
    const response = await api.post('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    })
    return response.data
  },
}

// Smart Insights API
export const smartInsightsApi = {
  getHealth: async (days: number = 30) => {
    const response = await api.get('/smart-insights/health', { params: { days }, timeout: ANALYTICS_TIMEOUT })
    return response.data
  },

  getRebalancing: async () => {
    const response = await api.get('/smart-insights/rebalancing', { timeout: ANALYTICS_TIMEOUT })
    return response.data
  },

  getAnomaliesImpact: async () => {
    const response = await api.get('/smart-insights/anomalies-impact', { timeout: ANALYTICS_TIMEOUT })
    return response.data
  },
}

// Goals API
export const goalsApi = {
  list: async () => {
    const response = await api.get('/goals')
    return response.data
  },

  create: async (data: { name: string; target_amount: number; currency?: string; target_date?: string; icon?: string; color?: string; notes?: string }) => {
    const response = await api.post('/goals', data)
    return response.data
  },

  update: async (id: string, data: Record<string, unknown>) => {
    const response = await api.patch(`/goals/${id}`, data)
    return response.data
  },

  sync: async (id: string) => {
    const response = await api.post(`/goals/${id}/sync`)
    return response.data
  },

  delete: async (id: string) => {
    await api.delete(`/goals/${id}`)
  },
}

export default api
