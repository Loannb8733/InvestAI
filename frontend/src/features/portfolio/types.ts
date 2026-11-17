import type { Schema } from '@/shared/api/client'

export type Portfolio = Schema<'PortfolioResponse'>
export type PortfolioPerformance = Schema<'PortfolioPerformance'>
export type Position = Schema<'PortfolioPosition'>
export type PortfolioHistory = Schema<'PortfolioHistory'>
export type SoldAsset = Schema<'SoldAsset'>
export type AssetCreate = Schema<'AssetCreate'>
export type AssetType = Schema<'AssetType'>
export type AssetTransaction = Schema<'TransactionWithAsset'>
export type SparklineSeries = Pick<Schema<'SparklineData'>, 'prices' | 'change_pct'>

export interface PositionGroup {
  symbol: string
  name: string | null
  asset_type: string
  assets: Position[]
  totalQuantity: number
  totalValue: number
  totalInvested: number
  totalGainLoss: number
  totalGainLossPercent: number
  currentPrice: number | null
  avgBuyPrice: number
  isMultiPlatform: boolean
}

export interface PlatformShare {
  platform: string
  value: number
  totalInvested: number
  gainLoss: number
  assets: { symbol: string; value: number }[]
  roi: number
}

export interface SoldGroup {
  symbol: string
  name: string | null
  asset_type: string
  assets: SoldAsset[]
  totalBought: number
  totalBoughtValue: number
  totalSold: number
  totalSoldValue: number
  realizedGain: number
  firstTx: string | null
  lastTx: string | null
}
