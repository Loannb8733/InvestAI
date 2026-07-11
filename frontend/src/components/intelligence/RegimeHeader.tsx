import { useQuery } from '@tanstack/react-query'
import { Activity } from 'lucide-react'
import { predictionsApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import { cn } from '@/lib/utils'
import type { MarketCycleData } from '@/types/predictions'

/**
 * Bandeau de régime de marché PARTAGÉ du hub Intelligence.
 *
 * Avant la refonte 3 piliers, le régime était affiché 5 fois (bannières
 * Prédictions ×3, carte SmartInsights, bannières de la matrice) avec 3
 * vocabulaires différents (bearish/markdown/accumulation…). Ici : UNE query,
 * UN affichage, UN vocabulaire — les piliers n'affichent plus le régime.
 */

/** Vocabulaire unifié : tous les alias backend → un libellé FR + un ton. */
const REGIME_LABELS: Record<string, { label: string; tone: 'gain' | 'loss' | 'warning' | 'neutral' }> = {
  bullish: { label: 'Haussier', tone: 'gain' },
  bull: { label: 'Haussier', tone: 'gain' },
  markup: { label: 'Haussier (markup)', tone: 'gain' },
  bearish: { label: 'Baissier', tone: 'loss' },
  bear: { label: 'Baissier', tone: 'loss' },
  markdown: { label: 'Baissier (markdown)', tone: 'loss' },
  accumulation: { label: 'Accumulation', tone: 'warning' },
  distribution: { label: 'Distribution', tone: 'warning' },
  neutral: { label: 'Neutre', tone: 'neutral' },
  sideways: { label: 'Latéral', tone: 'neutral' },
  stress: { label: 'Stress', tone: 'loss' },
  normal: { label: 'Normal', tone: 'neutral' },
  low: { label: 'Volatilité basse', tone: 'gain' },
}

const TONE_CLASSES: Record<string, string> = {
  gain: 'bg-gain/10 text-gain border-gain/30',
  loss: 'bg-loss/10 text-loss border-loss/30',
  warning: 'bg-warning/10 text-warning border-warning/30',
  neutral: 'bg-muted text-muted-foreground border-border',
}

function regimeDisplay(raw: string | null | undefined): { label: string; tone: string } {
  if (!raw) return { label: 'Indéterminé', tone: 'neutral' }
  const entry = REGIME_LABELS[raw.toLowerCase()]
  return entry ?? { label: raw, tone: 'neutral' }
}

export default function RegimeHeader() {
  const { data, isLoading } = useQuery<MarketCycleData>({
    queryKey: queryKeys.predictions.marketCycle,
    queryFn: predictionsApi.getMarketCycle,
    staleTime: 5 * 60_000,
    meta: { suppressGlobalError: true },
  })

  if (isLoading) {
    return <div className="h-9 rounded-lg bg-muted/50 animate-pulse" aria-hidden />
  }

  const regime = data?.market_regime
  if (!regime) return null

  const { label, tone } = regimeDisplay(regime.dominant_regime)
  const confidence = Math.round((regime.confidence ?? 0) * 100)
  const lowConfidence = confidence > 0 && confidence < 60

  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border px-3 py-2 text-sm',
        TONE_CLASSES[tone]
      )}
      role="status"
      aria-label={`Régime de marché : ${label}, confiance ${confidence} %`}
    >
      <span className="inline-flex items-center gap-1.5 font-medium">
        <Activity className="h-4 w-4" aria-hidden />
        Régime de marché : {label}
      </span>
      <span className="text-xs opacity-80 tabular">confiance {confidence} %</span>
      {lowConfidence && (
        <span className="text-xs opacity-70">— signal incertain, à traiter comme contexte, pas comme ordre</span>
      )}
      {regime.description && (
        <span className="text-xs opacity-70 basis-full sm:basis-auto">{regime.description}</span>
      )}
    </div>
  )
}
