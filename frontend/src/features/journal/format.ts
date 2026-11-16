import { Minus, TrendingDown, TrendingUp } from 'lucide-react'

export const SENTIMENT_OPTIONS = [
  { value: 'bullish', label: 'Bullish', icon: TrendingUp, color: 'text-gain' },
  { value: 'bearish', label: 'Bearish', icon: TrendingDown, color: 'text-loss' },
  { value: 'neutral', label: 'Neutre', icon: Minus, color: 'text-muted-foreground' },
]

export const sentimentLabel = (sentiment: string) =>
  sentiment === 'bullish' ? 'Bullish' : sentiment === 'bearish' ? 'Bearish' : 'Neutre'

export const fmtCount = (n: number) => Math.round(n).toString()

export const fmtHitRate = (v: number | null | undefined) => (v == null ? '—' : `${v.toFixed(0)} %`)

export const fmtPerf = (v: number | null | undefined) => {
  if (v == null) return '—'
  return `${v > 0 ? '+' : ''}${v.toFixed(1)} %`
}

export const perfClass = (v: number | null | undefined) => {
  if (v == null) return 'text-muted-foreground'
  if (v > 0) return 'text-gain'
  if (v < 0) return 'text-loss'
  return 'text-muted-foreground'
}

export const formatNoteDate = (dateString: string) =>
  new Date(dateString).toLocaleDateString('fr-FR', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })

export const parseTags = (tags: string | null): string[] => {
  if (!tags) return []
  return tags.split(',').map((t) => t.trim()).filter(Boolean)
}
