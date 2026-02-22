// User types
export interface User {
  id: string
  email: string
  role: 'admin' | 'user'
  firstName?: string
  lastName?: string
  mfaEnabled: boolean
  createdAt: string
  updatedAt: string
}

// Portfolio types
export interface Portfolio {
  id: string
  userId: string
  name: string
  description?: string
  createdAt: string
  updatedAt: string
}

// Asset types
export type AssetType = 'crypto' | 'stock' | 'etf' | 'real_estate' | 'bond' | 'other'

export interface Asset {
  id: string
  portfolioId: string
  symbol: string
  name?: string
  assetType: AssetType
  quantity: number
  avgBuyPrice: number
  currency: string
  exchange?: string
  createdAt: string
  updatedAt: string
}

export interface AssetWithMetrics extends Asset {
  currentPrice?: number
  currentValue?: number
  totalInvested?: number
  gainLoss?: number
  gainLossPercent?: number
  lastPriceUpdate?: string
}

// Transaction types
export type TransactionType =
  | 'buy'
  | 'sell'
  | 'transfer_in'
  | 'transfer_out'
  | 'staking_reward'
  | 'airdrop'
  | 'conversion_in'
  | 'conversion_out'

export interface Transaction {
  id: string
  assetId: string
  transactionType: TransactionType
  quantity: number
  price: number
  fee: number
  currency: string
  executedAt: string
  exchange?: string
  externalId?: string
  notes?: string
  createdAt: string
}

// Alert types
export type AlertCondition =
  | 'price_above'
  | 'price_below'
  | 'percent_change_up'
  | 'percent_change_down'
  | 'portfolio_value_above'
  | 'portfolio_value_below'

export interface Alert {
  id: string
  userId: string
  assetId?: string
  name: string
  condition: AlertCondition
  threshold: number
  currency: string
  isActive: boolean
  triggeredAt?: string
  triggeredCount: number
  notifyEmail: boolean
  notifyInApp: boolean
  createdAt: string
  updatedAt: string
}

// Dashboard metrics
export interface DashboardMetrics {
  totalValue: number
  totalGainLoss: number
  totalGainLossPercent: number
  dailyChange: number
  dailyChangePercent: number
  allocation: AllocationItem[]
  topGainers: AssetPerformance[]
  topLosers: AssetPerformance[]
}

export interface AllocationItem {
  type: AssetType
  value: number
  percentage: number
}

export interface AssetPerformance {
  symbol: string
  name?: string
  change: number
  changePercent: number
}

// API response types
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
  totalPages: number
}

export interface ApiError {
  detail: string
  status: number
}

// Display thresholds (adaptive, from backend)
export interface DisplayThresholds {
  fear_greed: {
    extreme_greed: number
    greed: number
    fear: number
    extreme_fear: number
  }
  trend_strength: {
    strong: number
    moderate: number
  }
  prediction_score: {
    good: number
    poor: number
  }
  sharpe: {
    excellent: number
    good: number
    fair: number
    neutral: number
  }
  volatility: {
    low: number
    high: number
    extreme: number
  }
  diversification: {
    good: number
    poor: number
  }
  beta: {
    high: number
    low: number
  }
  correlation: {
    strong_positive: number
    moderate_positive: number
    moderate_negative: number
    strong_negative: number
  }
}

// Default display thresholds (fallback when backend doesn't provide them)
export const DEFAULT_DISPLAY_THRESHOLDS: DisplayThresholds = {
  fear_greed: { extreme_greed: 75, greed: 55, fear: 45, extreme_fear: 25 },
  trend_strength: { strong: 4.0, moderate: 2.0 },
  prediction_score: { good: 70, poor: 45 },
  sharpe: { excellent: 1.5, good: 1.0, fair: 0.5, neutral: 0.0 },
  volatility: { low: 30, high: 50, extreme: 80 },
  diversification: { good: 60, poor: 40 },
  beta: { high: 1.0, low: 0.5 },
  correlation: { strong_positive: 0.7, moderate_positive: 0.4, moderate_negative: -0.3, strong_negative: -0.5 },
}
