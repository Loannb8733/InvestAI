import type { TransactionWithAssetInfo as Transaction } from '@/types'

/** Mise en forme et export de la page des transactions.
 *
 * Séparé de la page parce qu'ESLint refuse qu'un fichier exporte à la fois un
 * composant et des fonctions — la règle `react-refresh/only-export-components`,
 * la même qui avait imposé de sortir `fil-ariane.ts` de son fournisseur.
 * Ces trois fonctions sont pures : elles se testent sans monter l'écran.
 */

export function formatQuantity(quantity: number): string {
  const q = Number(quantity)
  if (!q || q === 0) return '0'
  quantity = q
  const absQuantity = Math.abs(quantity)
  if (absQuantity >= 1000) {
    return quantity.toLocaleString('fr-FR', { maximumFractionDigits: 2 })
  } else if (absQuantity >= 1) {
    return quantity.toLocaleString('fr-FR', { maximumFractionDigits: 4 })
  } else if (absQuantity >= 0.0001) {
    return quantity.toLocaleString('fr-FR', { maximumFractionDigits: 6 })
  } else {
    return quantity.toLocaleString('fr-FR', { maximumSignificantDigits: 4 })
  }
}

export function getDateRangeStart(value: string): Date | null {
  if (value === '0') return null
  if (value === 'ytd') {
    const now = new Date()
    return new Date(now.getFullYear(), 0, 1)  // January 1st of current year
  }
  const days = parseInt(value)
  if (isNaN(days) || days === 0) return null
  const date = new Date()
  date.setDate(date.getDate() - days)
  date.setHours(0, 0, 0, 0)
  return date
}

export function generateCSV(transactions: Transaction[]): string {
  /* Format destiné au **ré-import**, non à la lecture.
   *
   * Les nombres partent avec un point décimal parce que le parseur du serveur
   * fait `Decimal(quantity_str)`, qui refuse la virgule. C'est l'inverse de
   * l'export CSV du serveur (`report_transactions`), lui destiné à Excel en
   * locale française, et qui emploie la virgule depuis NEW-25.
   *
   * Deux fichiers, deux publics, deux conventions : « harmoniser » celui-ci
   * casserait le cycle export → ré-import. */
  // Types lisibles par la machine, dates ISO, décimales à point
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
  return '\uFEFF' + csvContent // BOM for Excel compatibility
}
