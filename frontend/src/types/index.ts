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
