export const queryKeys = {
  portfolios: {
    all: ['portfolios'] as const,
    list: () => [...queryKeys.portfolios.all, 'list'] as const,
    detail: (id: string) => [...queryKeys.portfolios.all, 'detail', id] as const,
    metrics: (id: string | null) => [...queryKeys.portfolios.all, 'metrics', id] as const,
    history: (id: string | null) => [...queryKeys.portfolios.all, 'history', id] as const,
    sparklines: (id: string | null) => [...queryKeys.portfolios.all, 'sparklines', id] as const,
  },

  assets: {
    all: ['assets'] as const,
    list: (portfolioId?: string) =>
      [...queryKeys.assets.all, 'list', ...(portfolioId ? [portfolioId] : [])] as const,
    detail: (id: string) => [...queryKeys.assets.all, 'detail', id] as const,
  },

  transactions: {
    all: ['transactions'] as const,
    list: (portfolioId?: string) =>
      [...queryKeys.transactions.all, 'list', ...(portfolioId ? [portfolioId] : [])] as const,
    detail: (id: string) => [...queryKeys.transactions.all, 'detail', id] as const,
    csvPlatforms: ['transactions', 'csvPlatforms'] as const,
  },

  dashboard: {
    all: ['dashboard'] as const,
    metrics: (days?: number) =>
      [...queryKeys.dashboard.all, 'metrics', ...(days !== undefined ? [days] : [])] as const,
    benchmarks: (days?: number) =>
      [...queryKeys.dashboard.all, 'benchmarks', ...(days !== undefined ? [days] : [])] as const,
    historical: (days?: number) =>
      [...queryKeys.dashboard.all, 'historical', ...(days !== undefined ? [days] : [])] as const,
    recent: (limit?: number) =>
      [...queryKeys.dashboard.all, 'recent', ...(limit !== undefined ? [limit] : [])] as const,
  },

  analytics: {
    all: ['analytics'] as const,
    global: (portfolioId?: string, days?: number) =>
      [...queryKeys.analytics.all, 'global', ...(portfolioId ? [portfolioId] : ['all']), ...(days !== undefined ? [days] : [])] as const,
    diversification: (portfolioId?: string, days?: number) =>
      [...queryKeys.analytics.all, 'diversification', ...(portfolioId ? [portfolioId] : ['all']), ...(days !== undefined ? [days] : [])] as const,
    correlation: (portfolioId?: string, days?: number) =>
      [...queryKeys.analytics.all, 'correlation', ...(portfolioId ? [portfolioId] : ['all']), ...(days !== undefined ? [days] : [])] as const,
    performance: (portfolioId?: string, period?: string) =>
      [...queryKeys.analytics.all, 'performance', ...(portfolioId ? [portfolioId] : ['all']), ...(period ? [period] : [])] as const,
    monteCarlo: (portfolioId?: string, horizon?: number) =>
      [...queryKeys.analytics.all, 'monteCarlo', ...(portfolioId ? [portfolioId] : ['all']), ...(horizon !== undefined ? [horizon] : [])] as const,
    xirr: (portfolioId?: string) =>
      [...queryKeys.analytics.all, 'xirr', ...(portfolioId ? [portfolioId] : ['all'])] as const,
    optimize: (portfolioId?: string, days?: number) =>
      [...queryKeys.analytics.all, 'optimize', ...(portfolioId ? [portfolioId] : ['all']), ...(days !== undefined ? [days] : [])] as const,
    stressTest: (portfolioId?: string) =>
      [...queryKeys.analytics.all, 'stressTest', ...(portfolioId ? [portfolioId] : ['all'])] as const,
    beta: (portfolioId?: string, days?: number) =>
      [...queryKeys.analytics.all, 'beta', ...(portfolioId ? [portfolioId] : ['all']), ...(days !== undefined ? [days] : [])] as const,
    historicalData: (days?: number) =>
      [...queryKeys.analytics.all, 'historicalData', ...(days !== undefined ? [days] : [])] as const,
  },

  predictions: {
    all: ['predictions'] as const,
    asset: (symbol: string, type?: string, days?: number) =>
      [...queryKeys.predictions.all, 'asset', symbol, ...(type ? [type] : []), ...(days !== undefined ? [days] : [])] as const,
    portfolio: (days?: number) =>
      [...queryKeys.predictions.all, 'portfolio', ...(days !== undefined ? [days] : [])] as const,
    anomalies: ['predictions', 'anomalies'] as const,
    marketSentiment: ['predictions', 'marketSentiment'] as const,
    marketEvents: ['predictions', 'marketEvents'] as const,
    marketCycle: ['predictions', 'marketCycle'] as const,
    backtest: (days?: number) =>
      ['predictions', 'backtest', ...(days !== undefined ? [days] : [])] as const,
    trackRecord: (symbol: string) =>
      ['predictions', 'trackRecord', symbol] as const,
    topAlpha: ['predictions', 'topAlpha'] as const,
    strategyMap: ['predictions', 'strategyMap'] as const,
    plannedOrders: ['predictions', 'plannedOrders'] as const,
  },

  alerts: {
    all: ['alerts'] as const,
    list: (activeOnly?: boolean) =>
      [...queryKeys.alerts.all, 'list', ...(activeOnly !== undefined ? [activeOnly] : [])] as const,
    conditions: ['alerts', 'conditions'] as const,
    summary: ['alerts', 'summary'] as const,
  },

  notifications: {
    all: ['notifications'] as const,
    list: ['notifications', 'list'] as const,
    unreadCount: ['notifications', 'unreadCount'] as const,
  },

  notes: {
    all: ['notes'] as const,
    list: (search?: string, tag?: string | null) =>
      [...queryKeys.notes.all, 'list', ...(search ? [search] : ['']), ...(tag ? [tag] : [''])] as const,
    summary: ['notes', 'summary'] as const,
  },

  calendar: {
    all: ['calendar'] as const,
    events: (showCompleted?: boolean, incomeOnly?: boolean) =>
      [...queryKeys.calendar.all, 'events', ...(showCompleted !== undefined ? [showCompleted] : []), ...(incomeOnly !== undefined ? [incomeOnly] : [])] as const,
    upcoming: (days?: number) =>
      [...queryKeys.calendar.all, 'upcoming', ...(days !== undefined ? [days] : [])] as const,
    summary: ['calendar', 'summary'] as const,
    eventTypes: ['calendar', 'eventTypes'] as const,
    marketEvents: ['calendar', 'marketEvents'] as const,
  },

  goals: {
    all: ['goals'] as const,
    list: ['goals', 'list'] as const,
  },

  apiKeys: {
    all: ['apiKeys'] as const,
    list: ['apiKeys', 'list'] as const,
  },

  exchanges: {
    all: ['exchanges'] as const,
    list: ['exchanges', 'list'] as const,
  },

  insights: {
    all: ['insights'] as const,
    fees: ['insights', 'fees'] as const,
    taxLossHarvesting: ['insights', 'taxLossHarvesting'] as const,
    passiveIncome: ['insights', 'passiveIncome'] as const,
    dcaBacktest: (symbol: string, assetType: string, amount: number, startYear: number) =>
      ['insights', 'dcaBacktest', symbol, assetType, amount, startYear] as const,
  },

  smartInsights: {
    all: ['smartInsights'] as const,
    health: (days: number) => [...queryKeys.smartInsights.all, 'health', days] as const,
    rebalancing: ['smartInsights', 'rebalancing'] as const,
    anomaliesImpact: ['smartInsights', 'anomaliesImpact'] as const,
    summary: (days: number) => [...queryKeys.smartInsights.all, 'summary', days] as const,
  },

  admin: {
    all: ['admin'] as const,
    users: ['admin', 'users'] as const,
  },

  reports: {
    all: ['reports'] as const,
    availableYears: ['reports', 'availableYears'] as const,
  },

  strategies: {
    all: ['strategies'] as const,
    list: ['strategies', 'list'] as const,
  },

  crowdfunding: {
    all: ['crowdfunding'] as const,
    list: ['crowdfunding', 'list'] as const,
    detail: (id: string) => ['crowdfunding', 'detail', id] as const,
    dashboard: ['crowdfunding', 'dashboard'] as const,
    performance: ['crowdfunding', 'performance'] as const,
    audits: ['crowdfunding', 'audits'] as const,
    audit: (id: string) => ['crowdfunding', 'audit', id] as const,
    stressTest: (id: string, delay: number) => ['crowdfunding', 'stress-test', id, delay] as const,
  },
} as const
