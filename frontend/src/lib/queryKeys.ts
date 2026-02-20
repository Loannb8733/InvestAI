export const queryKeys = {
  portfolios: {
    all: ['portfolios'] as const,
    list: () => [...queryKeys.portfolios.all, 'list'] as const,
    detail: (id: string) => [...queryKeys.portfolios.all, 'detail', id] as const,
    metrics: (id: string) => [...queryKeys.portfolios.all, 'metrics', id] as const,
    history: (id: string) => [...queryKeys.portfolios.all, 'history', id] as const,
  },

  assets: {
    all: ['assets'] as const,
    list: (portfolioId?: string) =>
      [...queryKeys.assets.all, 'list', ...(portfolioId ? [portfolioId] : [])] as const,
    detail: (id: string) => [...queryKeys.assets.all, 'detail', id] as const,
  },

  transactions: {
    all: ['transactions'] as const,
    list: (filters?: { asset_id?: string; portfolio_id?: string; skip?: number; limit?: number }) =>
      [...queryKeys.transactions.all, 'list', ...(filters ? [filters] : [])] as const,
    detail: (id: string) => [...queryKeys.transactions.all, 'detail', id] as const,
  },

  dashboard: {
    all: ['dashboard'] as const,
    metrics: (days?: number) =>
      [...queryKeys.dashboard.all, 'metrics', ...(days !== undefined ? [days] : [])] as const,
    historical: (days?: number) =>
      [...queryKeys.dashboard.all, 'historical', ...(days !== undefined ? [days] : [])] as const,
    recent: (limit?: number) =>
      [...queryKeys.dashboard.all, 'recent', ...(limit !== undefined ? [limit] : [])] as const,
  },

  analytics: {
    all: ['analytics'] as const,
    global: (days?: number) =>
      [...queryKeys.analytics.all, 'global', ...(days !== undefined ? [days] : [])] as const,
    correlation: ['analytics', 'correlation'] as const,
    diversification: ['analytics', 'diversification'] as const,
    riskMetrics: ['analytics', 'riskMetrics'] as const,
  },

  predictions: {
    all: ['predictions'] as const,
    asset: (symbol: string, type?: string, days?: number) =>
      [...queryKeys.predictions.all, 'asset', symbol, ...(type ? [type] : []), ...(days !== undefined ? [days] : [])] as const,
    portfolio: (days?: number) =>
      [...queryKeys.predictions.all, 'portfolio', ...(days !== undefined ? [days] : [])] as const,
    anomalies: ['predictions', 'anomalies'] as const,
  },

  alerts: {
    all: ['alerts'] as const,
    list: (activeOnly?: boolean) =>
      [...queryKeys.alerts.all, 'list', ...(activeOnly !== undefined ? [activeOnly] : [])] as const,
    summary: ['alerts', 'summary'] as const,
  },

  notifications: {
    all: ['notifications'] as const,
    list: ['notifications', 'list'] as const,
    unreadCount: ['notifications', 'unreadCount'] as const,
  },

  notes: {
    all: ['notes'] as const,
    list: (filters?: { tag?: string; asset_id?: string; search?: string }) =>
      [...queryKeys.notes.all, 'list', ...(filters ? [filters] : [])] as const,
  },

  calendar: {
    all: ['calendar'] as const,
    list: (filters?: { start_date?: string; end_date?: string; event_type?: string; show_completed?: boolean }) =>
      [...queryKeys.calendar.all, 'list', ...(filters ? [filters] : [])] as const,
    upcoming: (days?: number) =>
      [...queryKeys.calendar.all, 'upcoming', ...(days !== undefined ? [days] : [])] as const,
  },

  goals: {
    all: ['goals'] as const,
    list: ['goals', 'list'] as const,
  },

  apiKeys: {
    all: ['apiKeys'] as const,
    list: ['apiKeys', 'list'] as const,
  },
} as const
