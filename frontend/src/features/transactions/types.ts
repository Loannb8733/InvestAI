import type { Schema } from '@/shared/api/client'

export type Transaction = Schema<'TransactionWithAsset'>
export type TransactionType = Schema<'TransactionType'>
export type TransactionCreate = Schema<'TransactionCreate'>
export type TransactionUpdate = Schema<'TransactionUpdate'>
export type CsvImportResult = Schema<'CsvImportResult'>
export type AssetCreate = Schema<'AssetCreate'>

export interface TransactionPage {
  items: Transaction[]
  total: number
}

export interface ServerFilters {
  portfolio_id?: string
  transaction_type?: string
  exchange?: string
  asset_symbol?: string
  date_from?: string
  search?: string
}

export interface CurrencyTotals {
  bought: number
  sold: number
  fees: number
  netFlow: number
}

export interface TransactionStats {
  byCurrency: Record<string, CurrencyTotals>
  excludedCount: number
}

export type SortField = 'date' | 'type' | 'asset' | 'quantity' | 'price' | 'total' | 'fee'
export type SortDirection = 'asc' | 'desc'

export interface Choice {
  value: string
  count: number
}
