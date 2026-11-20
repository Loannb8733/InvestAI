import { http as api } from '@/shared/api/http'

// Dashboard API
export const dashboardApi = {
  getMetrics: async (days: number = 30) => {
    const response = await api.get('/dashboard', { params: { days } })
    return response.data
  },

  getHistoricalData: async (days: number = 30) => {
    const response = await api.get('/dashboard/historical-data', { params: { days } })
    return response.data
  },

  getBenchmarks: async (days: number = 90) => {
    const response = await api.get('/dashboard/benchmarks', { params: { days } })
    return response.data
  },

  getMunitions: async (monthlyDca: number = 300, profile: string = 'moderate') => {
    const response = await api.get('/dashboard/munitions', {
      params: { monthly_dca: monthlyDca, profile },
    })
    return response.data as {
      available_liquidity: number
      total_value: number
      liquidity_pct: number
      invested_pct: number
      next_signal_symbol: string | null
      next_signal_action: string | null
      next_signal_amount: number
      can_execute: boolean
      shortfall: number
      message: string | null
      profile: string
      deploy_to_risk: number
      keep_in_reserve: number
    }
  },
}

// Analytics API
const ANALYTICS_TIMEOUT = 120000 // 2 minutes — historical data fetches are slow

export interface PlatformDistributionItem {
  name: string
  value: number
  percentage: number
  trust_score: number
}

export const analyticsApi = {
  getPlatformDistribution: async (): Promise<PlatformDistributionItem[]> => {
    const response = await api.get('/analytics/distribution/platforms')
    return response.data
  },

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

  getPerformance: async (period: string = '30d', portfolioId?: string) => {
    const response = await api.get('/analytics/performance', {
      params: { period, ...(portfolioId ? { portfolio_id: portfolioId } : {}) },
      timeout: ANALYTICS_TIMEOUT,
    })
    return response.data
  },

  getMonteCarlo: async (
    horizon: number = 90,
    portfolioId?: string,
    annualWithdrawalRate?: number,
    terPercentage?: number,
    monthlyWithdrawal?: number,
  ) => {
    const response = await api.get('/analytics/monte-carlo', {
      params: {
        horizon,
        ...(portfolioId ? { portfolio_id: portfolioId } : {}),
        ...(annualWithdrawalRate ? { annual_withdrawal_rate: annualWithdrawalRate } : {}),
        ...(terPercentage ? { ter_percentage: terPercentage } : {}),
        ...(monthlyWithdrawal ? { monthly_withdrawal: monthlyWithdrawal } : {}),
      },
      timeout: ANALYTICS_TIMEOUT,
    })
    return response.data
  },

  getXirr: async (portfolioId?: string) => {
    const response = await api.get('/analytics/xirr', {
      params: portfolioId ? { portfolio_id: portfolioId } : {},
      timeout: ANALYTICS_TIMEOUT,
    })
    return response.data
  },

  getOptimize: async (objective: string = 'max_sharpe', days?: number) => {
    const response = await api.get('/analytics/optimize', {
      params: { objective, ...(days ? { days } : {}) },
      timeout: ANALYTICS_TIMEOUT,
    })
    return response.data
  },

  getStressTest: async (portfolioId?: string) => {
    const response = await api.get('/analytics/stress-test', {
      params: { ...(portfolioId ? { portfolio_id: portfolioId } : {}) },
      timeout: ANALYTICS_TIMEOUT,
    })
    return response.data
  },

  getBeta: async (days: number = 90, portfolioId?: string) => {
    const response = await api.get('/analytics/beta', {
      params: { days, ...(portfolioId ? { portfolio_id: portfolioId } : {}) },
      timeout: ANALYTICS_TIMEOUT,
    })
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

// Predictions API
export const predictionsApi = {

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

  getTopAlpha: async () => {
    const response = await api.get('/predictions/top-alpha', { timeout: ANALYTICS_TIMEOUT })
    return response.data
  },

  getMarketEvents: async () => {
    const response = await api.get('/predictions/events')
    return response.data
  },

  getMarketCycle: async () => {
    const response = await api.get('/predictions/market-cycle')
    return response.data
  },

  getStrategyMap: async () => {
    const response = await api.get('/predictions/strategy-map', { timeout: ANALYTICS_TIMEOUT })
    return response.data
  },

  getTrackRecord: async (symbol: string, limit: number = 20) => {
    const response = await api.get(`/predictions/track-record/${symbol}`, {
      params: { limit },
    })
    return response.data
  },

  getBacktest: async (days: number = 7) => {
    const response = await api.get('/predictions/backtest', { params: { days } })
    return response.data
  },

  validateSignal: async (params: { symbol?: string; amount_eur: number }) => {
    const response = await api.get('/predictions/validate-signal', {
      params,
      timeout: ANALYTICS_TIMEOUT,
    })
    return response.data
  },

  getPlannedOrders: async () => {
    const response = await api.get('/predictions/planned-orders')
    return response.data
  },

  updatePlannedOrder: async (id: string, status: string) => {
    const response = await api.patch(`/predictions/planned-orders/${id}`, { status })
    return response.data
  },

  createPlannedOrder: async (data: {
    symbol: string
    side: 'buy' | 'sell'
    amount_eur: number
    notes?: string
    source?: 'frontend' | 'telegram'
  }) => {
    const response = await api.post('/predictions/planned-orders', data)
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
    asset_id: string | null // null pour les alertes de portefeuille
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
export interface RebalancingDriftCategory {
  category: string
  label: string
  current_value: number
  current_pct: number
  target_pct: number
  drift_pct: number
  drift_eur: number
}

export interface RebalancingDrift {
  targets: Record<string, number> | null
  categories: RebalancingDriftCategory[]
  max_drift_pct: number
  total_crypto_value: number
}

export interface TaxSummary {
  year: number
  nb_cessions: number
  total_cessions: number
  total_plus_values: number
  total_moins_values: number
  net_plus_value: number
  flat_tax_30: number
  ir_12_8: number
  ps_17_2: number
}

export const reportsApi = {
  getAvailableYears: async () => {
    const response = await api.get('/reports/available-years')
    return response.data
  },

  /** Synthèse fiscale 2086 de l'année (vraie base imposable FR, JSON). */
  getTaxSummary: async (year: number): Promise<TaxSummary> => {
    const response = await api.get(`/reports/tax/${year}/summary`)
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

  downloadStockTaxPDF: async (year: number) => {
    const response = await api.get(`/reports/tax/securities/${year}/pdf`, {
      responseType: 'blob',
    })
    return response.data
  },

  downloadStockTaxExcel: async (year: number) => {
    const response = await api.get(`/reports/tax/securities/${year}/excel`, {
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

  downloadTransactionsExcel: async (year?: number) => {
    const params = year ? { year } : {}
    const response = await api.get('/reports/transactions/excel', {
      params,
      responseType: 'blob',
    })
    return response.data
  },

  downloadTransactionsCSV: async (year?: number) => {
    const params = year ? { year } : {}
    const response = await api.get('/reports/transactions/csv', {
      params,
      responseType: 'blob',
    })
    return response.data
  },

  getRebalancingReport: async (targetAllocations: Record<string, number>) => {
    const response = await api.post('/reports/rebalancing', {
      target_allocations: targetAllocations,
    })
    return response.data
  },

  /** Allocation cible persistée (null si jamais définie). */
  getRebalancingTargets: async (): Promise<{ targets: Record<string, number> | null }> => {
    const response = await api.get('/reports/rebalancing/targets')
    return response.data
  },

  saveRebalancingTargets: async (targetAllocations: Record<string, number>) => {
    const response = await api.put('/reports/rebalancing/targets', {
      target_allocations: targetAllocations,
    })
    return response.data
  },

  /** Écart actuel vs cible — version légère (sans estimation fiscale). */
  getRebalancingDrift: async (): Promise<RebalancingDrift> => {
    const response = await api.get('/reports/rebalancing/drift')
    return response.data
  },

  downloadRebalancingPDF: async (targetAllocations: Record<string, number>) => {
    const response = await api.post('/reports/rebalancing/pdf', {
      target_allocations: targetAllocations,
    }, {
      responseType: 'blob',
    })
    return response.data
  },
}

// Notes API
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

  getPassiveIncome: async () => {
    const response = await api.get('/calendar/passive-income')
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
    income_only?: boolean
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

  // FIRE probabiliste (Monte Carlo) — taux en DÉCIMAL (0.04 = 4 %).
  // Les champs omis sont pré-remplis côté backend (portefeuille live,
  // profil investisseur) et la source est échouée dans assumptions.defaults_from.
  fireProbabilistic: async (data: {
    current_value?: number
    monthly_contribution?: number
    annual_expenses: number
    withdrawal_rate?: number
    annual_return_mean?: number
    annual_volatility?: number
    inflation?: number
    index_contributions?: boolean
    years_horizon?: number
    n_paths?: number
  }) => {
    const response = await api.post('/simulations/fire-probabilistic', data)
    return response.data
  },

  projectPortfolio: async (data: {
    years?: number
    expected_return?: number
    expense_ratio?: number
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

  sendTelegramTest: async () => {
    const response = await api.post('/notifications/telegram/test')
    return response.data
  },
}

// Profile API (user self-service)

/** Profil investisseur (paramètres financiers). `null` = non renseigné. */
// Smart Insights API
export const smartInsightsApi = {
  getHealth: async (days: number = 30) => {
    const response = await api.get('/smart-insights/health', { params: { days }, timeout: ANALYTICS_TIMEOUT })
    return response.data
  },

  getAnomaliesImpact: async () => {
    const response = await api.get('/smart-insights/anomalies-impact', { timeout: ANALYTICS_TIMEOUT })
    return response.data
  },

  getSummary: async (days: number = 30) => {
    const response = await api.get('/smart-insights/summary', { params: { days }, timeout: ANALYTICS_TIMEOUT })
    return response.data as {
      health_score: number
      health_status: string
      top_insight: { title: string; message: string; severity: string; category: string } | null
      breakeven_pct: number | null
      anomaly_count: number
      regime: string | null
      generated_at: string
    }
  },
}

// Goals API
export const goalsApi = {
  list: async () => {
    const response = await api.get('/goals')
    return response.data
  },

  create: async (data: {
    name: string
    goal_type?: string
    target_amount: number
    currency?: string
    target_date?: string
    deadline_date?: string
    priority?: string
    strategy_type?: string
    icon?: string
    color?: string
    notes?: string
  }) => {
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

  projection: async (id: string, monthlyContribution: number = 0) => {
    const response = await api.get(`/goals/${id}/projection`, {
      params: { monthly_contribution: monthlyContribution },
    })
    return response.data
  },

  delete: async (id: string) => {
    await api.delete(`/goals/${id}`)
  },
}

export const crowdfundingApi = {
  list: async () => {
    const response = await api.get('/crowdfunding')
    return response.data
  },

  create: async (data: Record<string, unknown>) => {
    const response = await api.post('/crowdfunding', data)
    return response.data
  },

  get: async (id: string) => {
    const response = await api.get(`/crowdfunding/${id}`)
    return response.data
  },

  update: async (id: string, data: Record<string, unknown>) => {
    const response = await api.patch(`/crowdfunding/${id}`, data)
    return response.data
  },

  delete: async (id: string) => {
    await api.delete(`/crowdfunding/${id}`)
  },

  getDashboard: async () => {
    const response = await api.get('/crowdfunding/dashboard')
    return response.data
  },

  getPerformance: async () => {
    const response = await api.get('/crowdfunding/performance')
    return response.data
  },

  /** Rapport fiscal annuel : intérêts bruts / retenues à la source par plateforme, à réconcilier avec les IFU (formulaire 2561). */
  getTaxReport: async (year?: number) => {
    const response = await api.get('/crowdfunding/tax-report', {
      params: year !== undefined ? { year } : undefined,
    })
    return response.data
  },

  /** Échéancier consolidé : cash-flows attendus par mois (nets d'impôt) sur 24 mois. */
  getCashflowSchedule: async () => {
    const response = await api.get('/crowdfunding/cashflow-schedule')
    return response.data
  },

  syncCalendar: async () => {
    const response = await api.post('/crowdfunding/sync-calendar')
    return response.data
  },

  analyzeDocuments: async (files: File[], projectId?: string) => {
    const formData = new FormData()
    files.forEach((f) => formData.append('files', f))
    if (projectId) formData.append('project_id', projectId)
    const response = await api.post('/crowdfunding/analyze', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
    return response.data
  },

  listAudits: async () => {
    const response = await api.get('/crowdfunding/audits')
    return response.data
  },

  uploadDocuments: async (projectId: string, files: File[]) => {
    const formData = new FormData()
    files.forEach((f) => formData.append('files', f))
    const response = await api.post(`/crowdfunding/${projectId}/documents`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
    return response.data
  },

  downloadDocument: async (docId: string) => {
    const response = await api.get(`/crowdfunding/documents/${docId}/download`, {
      responseType: 'blob',
    })
    return response.data
  },

  createRepayment: async (projectId: string, data: {
    payment_date: string
    amount: number
    payment_type: 'interest' | 'capital' | 'both'
    interest_amount?: number
    capital_amount?: number
    tax_amount?: number
    notes?: string
  }) => {
    const response = await api.post(`/crowdfunding/${projectId}/repayments`, data)
    return response.data
  },

  deleteRepayment: async (projectId: string, repaymentId: string) => {
    await api.delete(`/crowdfunding/${projectId}/repayments/${repaymentId}`)
  },

  getStressTest: async (projectId: string, delayMonths: number) => {
    const response = await api.get(`/crowdfunding/${projectId}/stress-test`, {
      params: { delay_months: delayMonths },
    })
    return response.data
  },
}

// Strategies API
export const strategiesApi = {
  list: async () => {
    const response = await api.get('/strategies')
    return response.data
  },

  create: async (data: { name: string; description?: string; params?: Record<string, unknown>; actions?: { action: string; symbol?: string; amount?: number; currency?: string; reason?: string }[] }) => {
    const response = await api.post('/strategies', data)
    return response.data
  },

  update: async (id: string, data: { name?: string; description?: string; status?: string; params?: Record<string, unknown> }) => {
    const response = await api.patch(`/strategies/${id}`, data)
    return response.data
  },

  delete: async (id: string) => {
    await api.delete(`/strategies/${id}`)
  },

  accept: async (id: string) => {
    const response = await api.patch(`/strategies/${id}/accept`)
    return response.data
  },

  reject: async (id: string) => {
    const response = await api.patch(`/strategies/${id}/reject`)
    return response.data
  },

  updateAction: async (actionId: string, data: { status?: string; amount?: number }) => {
    const response = await api.patch(`/strategies/actions/${actionId}`, data)
    return response.data
  },

  getPerformance: async (id: string) => {
    const response = await api.get(`/strategies/${id}/performance`)
    return response.data
  },
}
