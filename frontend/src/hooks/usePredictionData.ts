import { useState, useMemo, useEffect, useRef } from 'react'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { useToast } from '@/hooks/use-toast'
import { formatCurrency } from '@/lib/utils'
import { predictionsApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import { type DisplayThresholds, DEFAULT_DISPLAY_THRESHOLDS } from '@/types'
import type {
  PortfolioPrediction,
  PortfolioPredictionSummary,
  Anomaly,
  MarketSentiment,
  MarketCycleData,
  BacktestData,
  WhatIfResult,
  ChartPoint,
  UnifiedAlert,
} from '@/types/predictions'

export function usePredictionData() {
  const [daysAhead, setDaysAhead] = useState(7)
  const [selectedAsset, setSelectedAsset] = useState<string | null>(null)
  const [whatIfSymbol, setWhatIfSymbol] = useState<string>('')
  const [whatIfChange, setWhatIfChange] = useState<number>(0)
  const [whatIfResult, setWhatIfResult] = useState<WhatIfResult | null>(null)
  const [whatIfLoading, setWhatIfLoading] = useState(false)
  const [showReality, setShowReality] = useState(false)
  const { toast } = useToast()

  // ── Queries ────────────────────────────────────────────────────────

  const { data: portfolioPredictions, isLoading: loadingPredictions } = useQuery({
    queryKey: queryKeys.predictions.portfolio(daysAhead),
    queryFn: () => predictionsApi.getPortfolioPredictions(daysAhead),
    placeholderData: keepPreviousData,
  })

  const { data: anomalies, isError: anomaliesError } = useQuery<Anomaly[]>({
    queryKey: queryKeys.predictions.anomalies,
    queryFn: predictionsApi.getAnomalies,
  })

  const { data: sentiment, isLoading: loadingSentiment, isError: sentimentError } = useQuery<MarketSentiment>({
    queryKey: queryKeys.predictions.marketSentiment,
    queryFn: predictionsApi.getMarketSentiment,
  })

  const { data: marketCycle, isLoading: loadingCycle } = useQuery<MarketCycleData>({
    queryKey: queryKeys.predictions.marketCycle,
    queryFn: predictionsApi.getMarketCycle,
  })

  const { data: backtestData, isLoading: loadingBacktest } = useQuery<BacktestData>({
    queryKey: queryKeys.predictions.backtest(daysAhead),
    queryFn: () => predictionsApi.getBacktest(daysAhead),
    enabled: showReality,
  })

  // ── Derived state ──────────────────────────────────────────────────

  const summary = portfolioPredictions?.summary as PortfolioPredictionSummary | undefined
  const predictions = portfolioPredictions?.predictions as PortfolioPrediction[] | undefined
  const dt: DisplayThresholds = (portfolioPredictions as Record<string, unknown>)?.display_thresholds as DisplayThresholds ?? DEFAULT_DISPLAY_THRESHOLDS

  // Reset What-If state when horizon changes
  useEffect(() => {
    setWhatIfResult(null)
    setWhatIfChange(0)
    setWhatIfSymbol('')
  }, [daysAhead])

  const effectiveWhatIfSymbol = whatIfSymbol || (predictions && predictions.length > 0 ? predictions[0].symbol : '')

  // ── Unified alerts ─────────────────────────────────────────────────

  const unifiedAlerts = useMemo((): UnifiedAlert[] => {
    const items: UnifiedAlert[] = []

    if (predictions) {
      for (const pred of predictions) {
        if (pred.predicted_price < pred.support_level && pred.support_level > 0) {
          items.push({
            symbol: pred.symbol,
            type: 'support_break',
            message: `${pred.symbol} pourrait casser son support à ${formatCurrency(pred.support_level)}`,
            severity: 'high',
            icon: 'shield',
            source: 'prediction',
          })
        }
        if (pred.predicted_price > pred.resistance_level && pred.resistance_level > 0) {
          items.push({
            symbol: pred.symbol,
            type: 'breakout',
            message: `${pred.symbol} pourrait franchir sa résistance à ${formatCurrency(pred.resistance_level)}`,
            severity: 'medium',
            icon: 'trending_up',
            source: 'prediction',
          })
        }
        if (pred.trend_strength > dt.trend_strength.strong) {
          items.push({
            symbol: pred.symbol,
            type: 'strong_trend',
            message: `Tendance ${pred.trend === 'bullish' ? 'haussière' : 'baissière'} forte sur ${pred.symbol} (${pred.trend_strength.toFixed(0)}%)`,
            severity: pred.trend === 'bearish' ? 'high' : 'low',
            icon: pred.trend === 'bullish' ? 'trending_up' : 'trending_down',
            source: 'prediction',
          })
        }
      }
    }

    if (sentiment?.signals) {
      for (const sig of sentiment.signals) {
        items.push({
          type: sig.type,
          message: sig.message,
          severity: sig.type === 'sell' ? 'high' : sig.type === 'buy' ? 'low' : 'medium',
          icon: sig.type === 'buy' ? 'trending_up' : sig.type === 'sell' ? 'trending_down' : 'zap',
          source: 'signal',
        })
      }
    }

    const sevOrder = { high: 0, medium: 1, low: 2 }
    return items.sort((a, b) => sevOrder[a.severity] - sevOrder[b.severity])
  }, [predictions, sentiment, dt])

  // ── Selected asset & chart data ────────────────────────────────────

  const selectedPrediction = predictions?.find(p => p.symbol === selectedAsset)

  const formatDateLabel = (dateStr: string) => {
    try {
      const d = new Date(dateStr)
      return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })
    } catch {
      return dateStr.slice(5)
    }
  }

  const chartData = useMemo((): ChartPoint[] => {
    if (!selectedPrediction?.predictions) return []

    const assetBacktest = showReality && backtestData
      ? backtestData.per_asset?.find(a => a.symbol === selectedPrediction.symbol)
      : null

    const realityPoints: ChartPoint[] = assetBacktest?.points?.map(p => ({
      date: formatDateLabel(p.date),
      actual: p.actual,
      predicted_past: p.predicted,
      isToday: false,
    })) ?? []

    const currentPoint: ChartPoint = {
      date: "Auj.",
      price: selectedPrediction.current_price,
      confidence_low: selectedPrediction.current_price,
      confidence_high: selectedPrediction.current_price,
      actual: showReality ? selectedPrediction.current_price : undefined,
      isToday: true,
    }

    const futurePoints: ChartPoint[] = selectedPrediction.predictions.map(p => ({
      date: formatDateLabel(p.date),
      price: p.price,
      confidence_low: p.confidence_low,
      confidence_high: p.confidence_high,
      isToday: false,
    }))

    if (showReality && realityPoints.length > 0) {
      return [...realityPoints, currentPoint, ...futurePoints]
    }

    return [currentPoint, ...futurePoints]
  }, [selectedPrediction, showReality, backtestData])

  const showSupportResistance = useMemo(() => {
    if (!selectedPrediction || !chartData.length) return false
    const allPrices = chartData.flatMap(d => [d.price, d.confidence_low, d.confidence_high, d.actual].filter((v): v is number => v != null))
    if (allPrices.length === 0) return false
    const minP = Math.min(...allPrices)
    const maxP = Math.max(...allPrices)
    const range = maxP - minP || maxP * 0.1
    const s = selectedPrediction.support_level
    const r = selectedPrediction.resistance_level
    return s > 0 && r > 0 && s > minP - range * 2 && r < maxP + range * 2
  }, [selectedPrediction, chartData])

  // ── What-If ────────────────────────────────────────────────────────

  const whatIfChangeRef = useRef(whatIfChange)
  whatIfChangeRef.current = whatIfChange

  const runWhatIf = async () => {
    if (!effectiveWhatIfSymbol) return
    setWhatIfResult(null)
    setWhatIfLoading(true)
    try {
      const result = await predictionsApi.whatIf([{ symbol: effectiveWhatIfSymbol, change_percent: whatIfChangeRef.current }])
      setWhatIfResult(result)
    } catch {
      toast({ title: 'Erreur', description: 'Impossible de lancer la simulation What-If', variant: 'destructive' })
    }
    setWhatIfLoading(false)
  }

  // ── Price formatter (handles tiny prices like PEPE) ────────────────

  const formatPrice = (value: number) => {
    if (value === 0) return '0'
    const abs = Math.abs(value)
    if (abs >= 1) return formatCurrency(value).replace(/[€\s]/g, '')
    if (abs < 0.0001) {
      const str = abs.toFixed(10)
      const match = str.match(/^0\.0*/)
      const zeros = match ? match[0].length - 2 : 0
      const significant = (abs * Math.pow(10, zeros)).toFixed(2)
      return `${significant}e-${zeros}`
    }
    return abs.toFixed(6)
  }

  // ── Alert counts ───────────────────────────────────────────────────

  const totalAlerts = unifiedAlerts.length
  const highAlerts = unifiedAlerts.filter(a => a.severity === 'high').length

  return {
    // State
    daysAhead,
    setDaysAhead,
    selectedAsset,
    setSelectedAsset,
    showReality,
    setShowReality,

    // What-If state
    whatIfSymbol: effectiveWhatIfSymbol,
    setWhatIfSymbol,
    whatIfChange,
    setWhatIfChange,
    whatIfResult,
    whatIfLoading,
    runWhatIf,

    // Query data
    predictions,
    summary,
    dt,
    anomalies,
    anomaliesError,
    sentiment,
    sentimentError,
    marketCycle,
    backtestData,

    // Loading states
    loadingPredictions,
    loadingSentiment,
    loadingCycle,
    loadingBacktest,

    // Derived data
    selectedPrediction,
    chartData,
    showSupportResistance,
    unifiedAlerts,
    totalAlerts,
    highAlerts,

    // Utilities
    formatPrice,
  }
}
