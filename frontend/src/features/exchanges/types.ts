import type { Schema } from '@/shared/api/client'

export type Exchange = Schema<'ExchangeInfo'>
export type ApiKey = Schema<'APIKeyResponse'>
export type ApiKeyCreate = Schema<'APIKeyCreate'>
export type ApiKeyUpdate = Schema<'APIKeyUpdate'>
export type TestResult = Schema<'ConnectionTestResult'>
export type BalanceGap = Schema<'BalanceGap'>
export type ColdWallet = Schema<'ColdWalletResponse'>

export interface GapCheck {
  gaps: BalanceGap[]
  checkedAt: Date
}
