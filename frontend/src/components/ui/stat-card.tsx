import { type ReactNode } from 'react'
import { Info, TrendingDown, TrendingUp, type LucideIcon } from 'lucide-react'
import TiltCard from '@/components/ui/tilt-card'
import NumberTicker from '@/components/ui/number-ticker'
import { SkeletonStatCard } from '@/components/ui/skeleton'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

/**
 * StatCard — la carte KPI financière du design system.
 *
 * Une surface 3D (TiltCard) portant : eyebrow + icône, grande valeur serif
 * animée (NumberTicker), badge de variation gain/perte, sous-ligne de contexte.
 *
 * États gérés nativement :
 * - `loading`  → squelette aux dimensions exactes (zéro layout shift) ;
 * - `privacy`  → valeur masquée (••••••), statique, sans animation ;
 * - valeur `null/undefined` → tiret long, pas de NaN affiché ;
 * - a11y : la carte est un `role="group"` étiqueté par son label, la
 *   variation est verbalisée (« +4,2 % sur 24h »), l'icône est décorative.
 */

interface StatCardProps {
  label: string
  /** Info-bulle accolée au label (l'UX Capital Net existante). */
  tooltip?: string
  icon?: LucideIcon
  value: number | null | undefined
  /** Formateur (ex: formatCurrency). Défaut : 2 décimales. */
  format?: (n: number) => string
  /** Variation en % — colore et signe le badge (gain/perte). */
  delta?: number | null
  /** Contexte de la variation (ex: "24h", "30j"). */
  deltaLabel?: string
  /** Formateur de la variation. Défaut : signe + 2 décimales + %. */
  formatDelta?: (n: number) => string
  /** Sous-ligne libre (ex: "12 actifs · dont 500 € de liquidité"). */
  hint?: ReactNode
  loading?: boolean
  privacy?: boolean
  /** Coupe le tilt 3D (grilles denses, listes longues). */
  static?: boolean
  /** `auto` : colore la valeur en gain/perte selon le signe du delta. */
  tone?: 'neutral' | 'auto'
  className?: string
}

const defaultFormatDelta = (n: number) =>
  `${n >= 0 ? '+' : ''}${n.toFixed(2).replace('.', ',')} %`

export default function StatCard({
  label,
  tooltip,
  icon: Icon,
  value,
  format = (n) => n.toFixed(2),
  delta,
  deltaLabel,
  formatDelta = defaultFormatDelta,
  hint,
  loading = false,
  privacy = false,
  static: isStatic = false,
  tone = 'neutral',
  className,
}: StatCardProps) {
  if (loading) return <SkeletonStatCard className={className} />

  const hasValue = value !== null && value !== undefined && Number.isFinite(value)
  const hasDelta = delta !== null && delta !== undefined && Number.isFinite(delta)
  const deltaPositive = hasDelta && (delta as number) >= 0
  const toned = tone === 'auto' && hasDelta && !privacy

  return (
    <TiltCard static={isStatic} className={className}>
      <div role="group" aria-label={label} className="flex h-full flex-col p-6">
        <div className="flex flex-row items-center justify-between pb-2">
          <span className="inline-flex items-center gap-1 text-sm font-medium">
            {label}
            {tooltip && (
              <TooltipProvider delayDuration={100}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      aria-label={`À propos de ${label}`}
                      className="cursor-help rounded-full focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
                    >
                      <Info className="h-3 w-3 text-muted-foreground" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent className="max-w-xs text-xs">{tooltip}</TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}
          </span>
          {Icon && <Icon aria-hidden className="h-4 w-4 text-muted-foreground" />}
        </div>

        <div
          className={cn(
            'font-serif text-2xl font-medium leading-tight',
            toned && (deltaPositive ? 'text-gain' : 'text-loss')
          )}
        >
          {privacy ? (
            <span aria-label="Valeur masquée">••••••</span>
          ) : hasValue ? (
            <NumberTicker value={value as number} format={format} />
          ) : (
            <span className="text-muted-foreground" aria-label="Donnée indisponible">
              —
            </span>
          )}
        </div>

        {(hasDelta || hint) && (
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
            {hasDelta && !privacy && (
              <span
                className={cn(
                  'inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-xs font-medium tabular',
                  deltaPositive ? 'bg-gain/10 text-gain' : 'bg-loss/10 text-loss'
                )}
                aria-label={`${formatDelta(delta as number)}${deltaLabel ? ` sur ${deltaLabel}` : ''}`}
              >
                {deltaPositive ? (
                  <TrendingUp aria-hidden className="h-3 w-3" />
                ) : (
                  <TrendingDown aria-hidden className="h-3 w-3" />
                )}
                {formatDelta(delta as number)}
                {deltaLabel && <span className="text-muted-foreground">· {deltaLabel}</span>}
              </span>
            )}
            {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
          </div>
        )}
      </div>
    </TiltCard>
  )
}
