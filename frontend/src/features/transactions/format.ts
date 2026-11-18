import type { Transaction } from './types'

export function formatQuantity(quantity: number): string {
  const q = Number(quantity)
  if (!q) return '0'
  const absQuantity = Math.abs(q)
  if (absQuantity >= 1000) return q.toLocaleString('fr-FR', { maximumFractionDigits: 2 })
  if (absQuantity >= 1) return q.toLocaleString('fr-FR', { maximumFractionDigits: 4 })
  if (absQuantity >= 0.0001) return q.toLocaleString('fr-FR', { maximumFractionDigits: 6 })
  return q.toLocaleString('fr-FR', { maximumSignificantDigits: 4 })
}

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
