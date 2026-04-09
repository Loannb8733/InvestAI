import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  Brain,
  Activity,
  TrendingUp,
  AlertTriangle,
  Target,
  Loader2,
  ChevronRight,
} from 'lucide-react'
import { smartInsightsApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import { Button } from '@/components/ui/button'

// ── Health gauge (circular SVG) ──

function HealthGauge({ score, status }: { score: number; status: string }) {
  const radius = 52
  const stroke = 8
  const circumference = 2 * Math.PI * radius
  const progress = (score / 100) * circumference
  const rotation = -90

  const color =
    score >= 80
      ? 'text-emerald-500'
      : score >= 65
        ? 'text-green-500'
        : score >= 50
          ? 'text-yellow-500'
          : score >= 30
            ? 'text-orange-500'
            : 'text-red-500'

  const strokeColor =
    score >= 80
      ? '#10b981'
      : score >= 65
        ? '#22c55e'
        : score >= 50
          ? '#eab308'
          : score >= 30
            ? '#f97316'
            : '#ef4444'

  const statusLabel: Record<string, string> = {
    excellent: 'Excellent',
    good: 'Bon',
    fair: 'Correct',
    poor: 'Faible',
    critical: 'Critique',
    unknown: '—',
  }

  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative h-[128px] w-[128px]">
        <svg className="h-full w-full" viewBox="0 0 128 128">
          {/* Background circle */}
          <circle
            cx="64"
            cy="64"
            r={radius}
            fill="none"
            strokeWidth={stroke}
            className="stroke-muted"
          />
          {/* Progress arc */}
          <circle
            cx="64"
            cy="64"
            r={radius}
            fill="none"
            strokeWidth={stroke}
            stroke={strokeColor}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={circumference - progress}
            transform={`rotate(${rotation} 64 64)`}
            className="transition-all duration-700 ease-out"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={`text-3xl font-bold tabular-nums ${color}`}>{score}</span>
          <span className="text-[10px] text-muted-foreground uppercase tracking-wider">
            / 100
          </span>
        </div>
      </div>
      <Badge
        variant="outline"
        className={`text-[10px] ${
          score >= 65
            ? 'border-emerald-500/30 text-emerald-600 bg-emerald-500/10'
            : score >= 50
              ? 'border-yellow-500/30 text-yellow-600 bg-yellow-500/10'
              : 'border-red-500/30 text-red-600 bg-red-500/10'
        }`}
      >
        {statusLabel[status] ?? status}
      </Badge>
    </div>
  )
}

// ── Flash indicator card ──

function FlashCard({
  icon: Icon,
  label,
  value,
  subtext,
  variant = 'default',
  onClick,
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: string
  subtext?: string
  variant?: 'default' | 'success' | 'warning' | 'danger'
  onClick?: () => void
}) {
  const variantStyles = {
    default: 'border-border/50',
    success: 'border-emerald-500/30 bg-emerald-500/5',
    warning: 'border-yellow-500/30 bg-yellow-500/5',
    danger: 'border-red-500/30 bg-red-500/5',
  }

  const iconColor = {
    default: 'text-muted-foreground',
    success: 'text-emerald-500',
    warning: 'text-yellow-500',
    danger: 'text-red-500',
  }

  return (
    <div
      className={`rounded-lg border p-3 flex flex-col gap-1 ${variantStyles[variant]} ${onClick ? 'cursor-pointer hover:bg-muted/50 transition-colors' : ''}`}
      onClick={onClick}
    >
      <div className="flex items-center gap-1.5">
        <Icon className={`h-3.5 w-3.5 ${iconColor[variant]}`} />
        <span className="text-[11px] text-muted-foreground">{label}</span>
      </div>
      <p className="text-lg font-bold tabular-nums leading-tight">{value}</p>
      {subtext && <p className="text-[10px] text-muted-foreground">{subtext}</p>}
    </div>
  )
}

// ── Main widget ──

export default function IASummaryWidget() {
  const navigate = useNavigate()

  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.smartInsights.summary(30),
    queryFn: () => smartInsightsApi.getSummary(30),
    staleTime: 120_000,
    refetchInterval: 300_000, // 5 min
  })

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    )
  }

  if (error || !data) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          Analyse IA indisponible
        </CardContent>
      </Card>
    )
  }

  const severityVariant = (s: string): 'danger' | 'warning' | 'success' => {
    if (s === 'critical') return 'danger'
    if (s === 'warning') return 'warning'
    return 'success'
  }

  const regimeLabels: Record<string, string> = {
    bullish: 'Haussier',
    bearish: 'Baissier',
    bottom: 'Creux',
    top: 'Sommet',
    unknown: '—',
  }

  const regimeVariant = (r: string | null): 'success' | 'warning' | 'danger' | 'default' => {
    if (r === 'bullish') return 'success'
    if (r === 'bottom') return 'warning'
    if (r === 'bearish' || r === 'top') return 'danger'
    return 'default'
  }

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-2 flex flex-row items-center justify-between">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Brain className="h-4 w-4 text-indigo-500" />
          Résumé IA
          {data.regime && (
            <Badge
              variant="outline"
              className={`ml-1 text-[10px] ${
                regimeVariant(data.regime) === 'success'
                  ? 'border-emerald-500/30 text-emerald-600 bg-emerald-500/10'
                  : regimeVariant(data.regime) === 'danger'
                    ? 'border-red-500/30 text-red-600 bg-red-500/10'
                    : regimeVariant(data.regime) === 'warning'
                      ? 'border-yellow-500/30 text-yellow-600 bg-yellow-500/10'
                      : ''
              }`}
            >
              {regimeLabels[data.regime] ?? data.regime}
            </Badge>
          )}
        </CardTitle>
        <Button
          variant="ghost"
          size="sm"
          className="text-xs h-7"
          onClick={() => navigate('/intelligence/smart-insights')}
        >
          Détails
          <ChevronRight className="h-3.5 w-3.5 ml-0.5" />
        </Button>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Bento grid: gauge + flash indicators */}
        <div className="grid grid-cols-3 gap-3">
          {/* Health gauge — spans 1 col on mobile, centered */}
          <div className="col-span-3 sm:col-span-1 flex justify-center">
            <HealthGauge score={data.health_score} status={data.health_status} />
          </div>

          {/* Flash indicators — 2 cols */}
          <div className="col-span-3 sm:col-span-2 grid grid-cols-2 gap-2">
            <FlashCard
              icon={Target}
              label="Breakeven"
              value={
                data.breakeven_pct != null
                  ? `${data.breakeven_pct >= 0 ? '+' : ''}${data.breakeven_pct.toFixed(1)}%`
                  : '—'
              }
              subtext="vs coût de revient"
              variant={
                data.breakeven_pct == null
                  ? 'default'
                  : data.breakeven_pct >= 0
                    ? 'success'
                    : 'danger'
              }
            />
            <FlashCard
              icon={TrendingUp}
              label="Top Alpha"
              value={data.top_alpha ? data.top_alpha.symbol : '—'}
              subtext={
                data.top_alpha
                  ? `Score ${data.top_alpha.alpha_score.toFixed(0)}/100`
                  : 'Aucun signal'
              }
              variant={data.top_alpha ? 'success' : 'default'}
              onClick={() => navigate('/intelligence/insights')}
            />
            <FlashCard
              icon={AlertTriangle}
              label="Anomalies"
              value={String(data.anomaly_count)}
              subtext={data.anomaly_count === 0 ? 'Tout est normal' : 'À surveiller'}
              variant={
                data.anomaly_count === 0
                  ? 'success'
                  : data.anomaly_count <= 2
                    ? 'warning'
                    : 'danger'
              }
              onClick={() => navigate('/intelligence/smart-insights')}
            />
            <FlashCard
              icon={Activity}
              label="Régime"
              value={data.regime ? (regimeLabels[data.regime] ?? data.regime) : '—'}
              subtext="Marché global"
              variant={regimeVariant(data.regime)}
            />
          </div>
        </div>

        {/* Top insight card */}
        {data.top_insight && (
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <div
                  className={`rounded-lg border p-3 cursor-pointer hover:bg-muted/50 transition-colors ${
                    data.top_insight.severity === 'critical'
                      ? 'border-red-500/30 bg-red-500/5'
                      : data.top_insight.severity === 'warning'
                        ? 'border-yellow-500/30 bg-yellow-500/5'
                        : 'border-border/50'
                  }`}
                  onClick={() => navigate('/intelligence/smart-insights')}
                >
                  <div className="flex items-start gap-2">
                    <Brain className={`h-4 w-4 mt-0.5 shrink-0 ${
                      data.top_insight.severity === 'critical'
                        ? 'text-red-500'
                        : data.top_insight.severity === 'warning'
                          ? 'text-yellow-500'
                          : 'text-indigo-500'
                    }`} />
                    <div className="min-w-0">
                      <p className="text-sm font-medium leading-tight">{data.top_insight.title}</p>
                      <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                        {data.top_insight.message}
                      </p>
                    </div>
                    <Badge
                      variant="outline"
                      className={`shrink-0 text-[9px] ${
                        severityVariant(data.top_insight.severity) === 'danger'
                          ? 'border-red-500/30 text-red-600'
                          : severityVariant(data.top_insight.severity) === 'warning'
                            ? 'border-yellow-500/30 text-yellow-600'
                            : 'border-emerald-500/30 text-emerald-600'
                      }`}
                    >
                      {data.top_insight.severity === 'critical'
                        ? 'Critique'
                        : data.top_insight.severity === 'warning'
                          ? 'Attention'
                          : 'Info'}
                    </Badge>
                  </div>
                </div>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="max-w-sm">
                <p className="text-sm">{data.top_insight.message}</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}

        {/* Data freshness */}
        <p className="text-[10px] text-muted-foreground text-right">
          Analyse du {new Date(data.generated_at).toLocaleString('fr-FR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
        </p>
      </CardContent>
    </Card>
  )
}
