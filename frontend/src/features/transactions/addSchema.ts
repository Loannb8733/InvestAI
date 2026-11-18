import { z } from 'zod'

export const addSchema = z.object({
  asset_id: z.string().min(1, 'Sélectionnez un actif'),
  transaction_type: z.enum([
    'buy',
    'sell',
    'transfer_in',
    'transfer_out',
    'staking_reward',
    'airdrop',
    'conversion_in',
    'conversion_out',
    'staking',
    'unstaking',
  ]),
  quantity: z.coerce.number().positive('Quantité doit être positive'),
  price: z.coerce.number().min(0, 'Prix invalide'),
  fee: z.coerce.number().min(0).default(0),
  executed_at: z.string().optional(),
  exchange: z.string().max(50).optional(),
  notes: z.string().max(500).optional(),
})

export type AddInput = z.input<typeof addSchema>
export type AddOutput = z.output<typeof addSchema>

export const toNum = (v: unknown) => {
  const n = Number(v)
  return isNaN(n) ? 0 : n
}
