import type { Transaction, TransactionType, TransactionUpdate } from './types'

export interface EditDraft {
  transactionType: TransactionType | ''
  quantity: string
  price: string
  fee: string
  feeCurrency: string
  currency: string
  executedDate: string
  executedTime: string
  exchange: string
  notes: string
}

export function draftOf(tx: Transaction, previous: EditDraft): EditDraft {
  const executed = tx.executed_at ? new Date(tx.executed_at) : null
  return {
    transactionType: tx.transaction_type,
    quantity: tx.quantity.toString(),
    price: tx.price.toString(),
    fee: (tx.fee ?? 0).toString(),
    feeCurrency: tx.fee_currency || tx.asset_symbol || '',
    currency: tx.currency || 'EUR',
    executedDate: executed ? executed.toISOString().split('T')[0] : previous.executedDate,
    executedTime: executed ? executed.toTimeString().slice(0, 5) : previous.executedTime,
    exchange: tx.exchange || '',
    notes: tx.notes || '',
  }
}

export const EMPTY_DRAFT: EditDraft = {
  transactionType: '',
  quantity: '',
  price: '',
  fee: '',
  feeCurrency: '',
  currency: '',
  executedDate: '',
  executedTime: '',
  exchange: '',
  notes: '',
}

function changedDate(tx: Transaction, draft: EditDraft): string | undefined {
  if (!draft.executedDate || !draft.executedTime) return undefined
  const executedAt = `${draft.executedDate}T${draft.executedTime}:00`
  const before = tx.executed_at ? new Date(tx.executed_at).getTime() : null
  return before === null || before !== new Date(executedAt).getTime() ? executedAt : undefined
}

export function changesOf(tx: Transaction, draft: EditDraft): TransactionUpdate {
  const updates: TransactionUpdate = {}
  const quantity = parseFloat(draft.quantity)
  const price = parseFloat(draft.price)
  const fee = parseFloat(draft.fee)
  if (draft.transactionType && draft.transactionType !== tx.transaction_type) updates.transaction_type = draft.transactionType
  if (!isNaN(quantity) && quantity !== tx.quantity) updates.quantity = quantity
  if (!isNaN(price) && price !== tx.price) updates.price = price
  if (!isNaN(fee) && fee !== (tx.fee ?? 0)) updates.fee = fee
  if (draft.feeCurrency && draft.feeCurrency !== (tx.fee_currency || '')) updates.fee_currency = draft.feeCurrency
  if (draft.currency && draft.currency !== tx.currency) updates.currency = draft.currency
  const executedAt = changedDate(tx, draft)
  if (executedAt) updates.executed_at = executedAt
  if (draft.exchange !== (tx.exchange || '')) updates.exchange = draft.exchange || undefined
  if (draft.notes !== (tx.notes || '')) updates.notes = draft.notes
  return updates
}

export const draftTotal = (draft: EditDraft) => {
  const toNum = (v: string) => {
    const n = parseFloat(v)
    return isNaN(n) ? 0 : n
  }
  return toNum(draft.quantity) * toNum(draft.price) + toNum(draft.fee)
}
