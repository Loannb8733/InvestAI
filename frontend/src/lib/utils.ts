import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Point unique de formatage des montants (ARC-11).
 *
 * `maximumFractionDigits` existe pour les affichages qui arrondissent
 * volontairement — une enveloppe d'investissement, un montant proposé — sans
 * quoi ces cas justifieraient un `Intl.NumberFormat` local, et le formatage se
 * remettrait à diverger d'un écran à l'autre. Passer 0 arrondit aussi le
 * minimum : demander 2 décimales minimum pour 0 maximum lève un RangeError.
 */
export function formatCurrency(
  value: number | string | null | undefined,
  currency = "EUR",
  options?: { maximumFractionDigits?: number },
): string {
  if (value == null) return "—"
  const num = typeof value === 'string' ? parseFloat(value) : value
  if (!Number.isFinite(num)) return "—"
  const max = options?.maximumFractionDigits ?? 2
  return new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency,
    minimumFractionDigits: Math.min(2, max),
    maximumFractionDigits: max,
  }).format(num)
}

export function formatPercent(value: number | string | null | undefined): string {
  if (value == null) return "—"
  const num = typeof value === 'string' ? parseFloat(value) : value
  if (!Number.isFinite(num)) return "—"
  return new Intl.NumberFormat("fr-FR", {
    style: "percent",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num / 100)
}

export function formatDate(dateString: string | null | undefined): string {
  if (!dateString) return "—"
  return new Date(dateString).toLocaleDateString("fr-FR", {
    day: "numeric",
    month: "short",
    year: "numeric",
  })
}

export function formatDateTime(dateString: string | null | undefined): string {
  if (!dateString) return "—"
  return new Date(dateString).toLocaleDateString("fr-FR", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}
