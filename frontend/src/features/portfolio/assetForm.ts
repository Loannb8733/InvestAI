import { z } from 'zod'
import type { AssetCreate } from './types'

export const ASSET_TYPES = [
  { value: 'crypto', label: 'Crypto-monnaie' },
  { value: 'stock', label: 'Action' },
  { value: 'etf', label: 'ETF' },
  { value: 'real_estate', label: 'Immobilier' },
  { value: 'bond', label: 'Obligation' },
  { value: 'other', label: 'Autre' },
] as const

export const assetFormSchema = z
  .object({
    asset_type: z.enum(['crypto', 'stock', 'etf', 'real_estate', 'bond', 'other']),
    symbol: z.string().optional(),
    name: z.string().optional(),
    quantity: z.coerce.number().optional(),
    avg_buy_price: z.coerce.number().optional(),
    exchange: z.string().optional(),
    project_name: z.string().optional(),
    invested_amount: z.coerce.number().optional(),
    interest_rate: z.coerce.number().optional(),
    maturity_date: z.string().optional(),
    currency: z.string().default('EUR'),
  })
  .superRefine((data, ctx) => {
    if (data.asset_type === 'real_estate') {
      if (!data.project_name?.trim()) {
        ctx.addIssue({ code: 'custom', message: 'Nom du projet requis', path: ['project_name'] })
      }
      if (!data.invested_amount || data.invested_amount <= 0) {
        ctx.addIssue({ code: 'custom', message: 'Montant doit être supérieur à 0', path: ['invested_amount'] })
      }
      return
    }
    if (!data.symbol?.trim()) {
      ctx.addIssue({ code: 'custom', message: 'Symbole requis', path: ['symbol'] })
    }
    if (data.quantity === undefined || data.quantity < 0) {
      ctx.addIssue({ code: 'custom', message: 'Quantité invalide (≥ 0)', path: ['quantity'] })
    }
    if (data.avg_buy_price === undefined || data.avg_buy_price < 0) {
      ctx.addIssue({ code: 'custom', message: 'Prix invalide (≥ 0)', path: ['avg_buy_price'] })
    }
  })

export type AssetFormInput = z.input<typeof assetFormSchema>
export type AssetFormData = z.output<typeof assetFormSchema>

export const ASSET_FORM_DEFAULTS: AssetFormInput = {
  asset_type: 'crypto',
  quantity: 0,
  avg_buy_price: 0,
  currency: 'EUR',
  project_name: '',
  invested_amount: 0,
  interest_rate: 0,
  maturity_date: '',
}

const projectSymbol = (projectName: string) =>
  projectName
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .substring(0, 20)

export function assetBody(data: AssetFormData, portfolioId: string): AssetCreate {
  if (data.asset_type === 'real_estate') {
    const projectName = data.project_name ?? ''
    const investedAmount = data.invested_amount ?? 0
    return {
      portfolio_id: portfolioId,
      symbol: projectSymbol(projectName),
      name: projectName,
      asset_type: 'real_estate',
      quantity: 1,
      avg_buy_price: investedAmount,
      currency: 'EUR',
      exchange: data.exchange || undefined,
      invested_amount: investedAmount,
      interest_rate: data.interest_rate || undefined,
      maturity_date: data.maturity_date || undefined,
      project_status: 'active',
    }
  }
  return {
    portfolio_id: portfolioId,
    symbol: (data.symbol ?? '').toUpperCase(),
    name: data.name || undefined,
    asset_type: data.asset_type,
    quantity: data.quantity ?? 0,
    avg_buy_price: data.avg_buy_price ?? 0,
    currency: 'EUR',
    exchange: data.exchange || undefined,
  }
}
