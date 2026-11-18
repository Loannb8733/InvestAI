import type { AssetCreate } from './types'

export interface AssetDraft {
  symbol: string
  name: string
  type: string
  exchange: string
  invested: string
  rate: string
  maturity: string
}

export const EMPTY_ASSET_DRAFT: AssetDraft = {
  symbol: '',
  name: '',
  type: 'crypto',
  exchange: '',
  invested: '',
  rate: '',
  maturity: '',
}

export const ASSET_TYPES = [
  { value: 'crypto', label: 'Crypto' },
  { value: 'stock', label: 'Action' },
  { value: 'etf', label: 'ETF' },
  { value: 'real_estate', label: 'Immobilier' },
  { value: 'bond', label: 'Obligation' },
  { value: 'fiat', label: 'Fiat' },
]

export const isRealEstate = (draft: AssetDraft) => draft.type === 'real_estate'

const isIdentified = (draft: AssetDraft) =>
  isRealEstate(draft) ? !!draft.name.trim() && !!draft.invested : !!draft.symbol.trim()

export const canCreateAsset = (draft: AssetDraft) => isIdentified(draft) && !!draft.exchange.trim()

export function assetBody(draft: AssetDraft, portfolioId: string): AssetCreate | null {
  const realEstate = isRealEstate(draft)
  if (!isIdentified(draft) || !portfolioId) return null
  const symbol = realEstate
    ? draft.name.trim().substring(0, 18).toUpperCase().replace(/\s+/g, '-')
    : draft.symbol.trim().toUpperCase()
  const amount = parseFloat(draft.invested) || 0
  return {
    portfolio_id: portfolioId,
    symbol,
    name: draft.name.trim() || symbol,
    asset_type: draft.type as AssetCreate['asset_type'],
    ...(draft.exchange ? { exchange: draft.exchange } : {}),
    ...(realEstate
      ? {
          quantity: 1,
          avg_buy_price: amount,
          invested_amount: amount,
          interest_rate: parseFloat(draft.rate) || undefined,
          maturity_date: draft.maturity || undefined,
          project_status: 'active',
        }
      : {}),
  }
}
