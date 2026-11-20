import { formatCurrency, formatQuantity } from '@/lib/utils'
import type { Transaction } from './types'

const FIAT = new Set(['EUR', 'USD', 'GBP', 'CHF'])

export const formatAmount = (value: number, currency: string) =>
  FIAT.has(currency) ? formatCurrency(value, currency) : `${formatQuantity(value)} ${currency}`

export function getDateRangeStart(value: string): Date | null {
  if (value === '0') return null
  if (value === 'ytd') return new Date(new Date().getFullYear(), 0, 1)
  const days = parseInt(value)
  if (isNaN(days) || days === 0) return null
  const date = new Date()
  date.setDate(date.getDate() - days)
  date.setHours(0, 0, 0, 0)
  return date
}

export function localDay(date: Date | null): string | undefined {
  if (!date) return undefined
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function generateCSV(transactions: Transaction[]): string {
  const headers = ['symbol', 'type', 'quantity', 'price', 'fee', 'date', 'notes']
  const rows = transactions.map((tx) => [
    tx.asset_symbol,
    tx.transaction_type,
    tx.quantity.toString(),
    tx.price.toString(),
    (tx.fee || 0).toString(),
    new Date(tx.executed_at || tx.created_at).toISOString().replace('T', ' ').substring(0, 19),
    (tx.notes || '').replace(/;/g, ',').replace(/\n/g, ' '),
  ])
  const csvContent = [headers.join(';'), ...rows.map((row) => row.join(';'))].join('\n')
  return '﻿' + csvContent
}

export const today = () => new Date().toISOString().split('T')[0]

export function saveFile(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  window.URL.revokeObjectURL(url)
  document.body.removeChild(a)
}
