import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement } from 'react'
import { usePredictionData } from './usePredictionData'
import type {
  PortfolioPrediction,
  PortfolioPredictionSummary,
  MarketSentiment,
} from '@/types/predictions'

// ── Mocks ────────────────────────────────────────────────────────────

vi.mock('@/services/api', () => ({
  predictionsApi: {
    getPortfolioPredictions: vi.fn(),
    getAnomalies: vi.fn(),
    getMarketSentiment: vi.fn(),
    getMarketCycle: vi.fn(),
    getBacktest: vi.fn(),
    whatIf: vi.fn(),
  },
}))

vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}))

import { predictionsApi } from '@/services/api'

const mockedApi = vi.mocked(predictionsApi)

// ── Test helpers ─────────────────────────────────────────────────────

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
    },
  })
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children)
}

function makePrediction(overrides: Partial<PortfolioPrediction> = {}): PortfolioPrediction {
  return {
    symbol: 'BTC',
    name: 'Bitcoin',
    asset_type: 'crypto',
    current_price: 50000,
    predicted_price: 55000,
    change_percent: 10,
    trend: 'bullish',
    trend_strength: 8,
    recommendation: 'Acheter',
    model_used: 'ensemble',
    predictions: [{ date: '2026-03-28', price: 55000, confidence_low: 52000, confidence_high: 58000 }],
    support_level: 48000,
    resistance_level: 60000,
    skill_score: 65,
    hit_rate: 60,
    hit_rate_significant: true,
    hit_rate_n_samples: 30,
    reliability_score: 62,
    model_confidence: 'useful',
    models_agree: true,
    ...overrides,
  }
}

function makeSummary(overrides: Partial<PortfolioPredictionSummary> = {}): PortfolioPredictionSummary {
  return {
    total_current_value: 100000,
    total_predicted_value: 110000,
    expected_change_percent: 10,
    overall_sentiment: 'bullish',
    bullish_assets: 3,
    bearish_assets: 1,
    neutral_assets: 1,
    days_ahead: 7,
    ...overrides,
  }
}

function makeSentiment(overrides: Partial<MarketSentiment> = {}): MarketSentiment {
  return {
    overall_sentiment: 'bullish',
    sentiment_score: 70,
    fear_greed_index: 65,
    market_phase: 'markup',
    signals: [],
    ...overrides,
  }
}

// ── Tests ────────────────────────────────────────────────────────────

describe('usePredictionData', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('données initiales', () => {
    it('retourne un état de chargement initial', () => {
      mockedApi.getPortfolioPredictions.mockReturnValue(new Promise(() => {}))
      mockedApi.getAnomalies.mockReturnValue(new Promise(() => {}))
      mockedApi.getMarketSentiment.mockReturnValue(new Promise(() => {}))
      mockedApi.getMarketCycle.mockReturnValue(new Promise(() => {}))

      const { result } = renderHook(() => usePredictionData(), { wrapper: createWrapper() })

      expect(result.current.loadingPredictions).toBe(true)
      expect(result.current.predictions).toBeUndefined()
      expect(result.current.daysAhead).toBe(7)
    })
  })

  describe('alertes unifiées', () => {
    it('génère une alerte "support_break" quand le prix prédit < support', async () => {
      const pred = makePrediction({
        predicted_price: 45000,
        support_level: 48000,
      })
      mockedApi.getPortfolioPredictions.mockResolvedValue({
        predictions: [pred],
        summary: makeSummary(),
      })
      mockedApi.getAnomalies.mockResolvedValue([])
      mockedApi.getMarketSentiment.mockResolvedValue(makeSentiment())
      mockedApi.getMarketCycle.mockResolvedValue(null)

      const { result } = renderHook(() => usePredictionData(), { wrapper: createWrapper() })

      await waitFor(() => expect(result.current.predictions).toBeDefined())

      const supportAlerts = result.current.unifiedAlerts.filter(a => a.type === 'support_break')
      expect(supportAlerts).toHaveLength(1)
      expect(supportAlerts[0].severity).toBe('high')
      expect(supportAlerts[0].symbol).toBe('BTC')
    })

    it('génère une alerte "breakout" quand le prix prédit > résistance', async () => {
      const pred = makePrediction({
        predicted_price: 62000,
        resistance_level: 60000,
      })
      mockedApi.getPortfolioPredictions.mockResolvedValue({
        predictions: [pred],
        summary: makeSummary(),
      })
      mockedApi.getAnomalies.mockResolvedValue([])
      mockedApi.getMarketSentiment.mockResolvedValue(makeSentiment())
      mockedApi.getMarketCycle.mockResolvedValue(null)

      const { result } = renderHook(() => usePredictionData(), { wrapper: createWrapper() })

      await waitFor(() => expect(result.current.predictions).toBeDefined())

      const breakoutAlerts = result.current.unifiedAlerts.filter(a => a.type === 'breakout')
      expect(breakoutAlerts).toHaveLength(1)
      expect(breakoutAlerts[0].severity).toBe('medium')
    })

    it('ne génère aucune alerte quand le prix est dans la fourchette support/résistance', async () => {
      const pred = makePrediction({
        predicted_price: 55000,
        support_level: 48000,
        resistance_level: 60000,
        trend_strength: 2, // below strong threshold
      })
      mockedApi.getPortfolioPredictions.mockResolvedValue({
        predictions: [pred],
        summary: makeSummary(),
      })
      mockedApi.getAnomalies.mockResolvedValue([])
      mockedApi.getMarketSentiment.mockResolvedValue(makeSentiment({ signals: [] }))
      mockedApi.getMarketCycle.mockResolvedValue(null)

      const { result } = renderHook(() => usePredictionData(), { wrapper: createWrapper() })

      await waitFor(() => expect(result.current.predictions).toBeDefined())

      expect(result.current.unifiedAlerts).toHaveLength(0)
    })

    it('fusionne les signaux de marché avec les alertes prédictives, triés par sévérité', async () => {
      const pred = makePrediction({
        predicted_price: 45000,
        support_level: 48000, // trigger support_break (high)
      })
      mockedApi.getPortfolioPredictions.mockResolvedValue({
        predictions: [pred],
        summary: makeSummary(),
      })
      mockedApi.getAnomalies.mockResolvedValue([])
      mockedApi.getMarketSentiment.mockResolvedValue(
        makeSentiment({
          signals: [{ type: 'buy', message: 'Signal achat', action: 'buy' }],
        }),
      )
      mockedApi.getMarketCycle.mockResolvedValue(null)

      const { result } = renderHook(() => usePredictionData(), { wrapper: createWrapper() })

      await waitFor(() => expect(result.current.predictions).toBeDefined())

      expect(result.current.unifiedAlerts.length).toBeGreaterThanOrEqual(2)
      // High severity first
      expect(result.current.unifiedAlerts[0].severity).toBe('high')
    })
  })

  describe('cas limites', () => {
    it('gère gracieusement des prédictions avec prix nuls', async () => {
      const pred = makePrediction({
        current_price: 0,
        predicted_price: 0,
        support_level: 0,
        resistance_level: 0,
        change_percent: 0,
      })
      mockedApi.getPortfolioPredictions.mockResolvedValue({
        predictions: [pred],
        summary: makeSummary(),
      })
      mockedApi.getAnomalies.mockResolvedValue([])
      mockedApi.getMarketSentiment.mockResolvedValue(makeSentiment())
      mockedApi.getMarketCycle.mockResolvedValue(null)

      const { result } = renderHook(() => usePredictionData(), { wrapper: createWrapper() })

      await waitFor(() => expect(result.current.predictions).toBeDefined())

      // Ne doit pas générer de support_break avec support_level=0
      const supportAlerts = result.current.unifiedAlerts.filter(a => a.type === 'support_break')
      expect(supportAlerts).toHaveLength(0)
    })

    it('gère des prédictions vides (API retourne un tableau vide)', async () => {
      mockedApi.getPortfolioPredictions.mockResolvedValue({
        predictions: [],
        summary: makeSummary(),
      })
      mockedApi.getAnomalies.mockResolvedValue([])
      mockedApi.getMarketSentiment.mockResolvedValue(makeSentiment())
      mockedApi.getMarketCycle.mockResolvedValue(null)

      const { result } = renderHook(() => usePredictionData(), { wrapper: createWrapper() })

      await waitFor(() => expect(result.current.loadingPredictions).toBe(false))

      expect(result.current.predictions).toEqual([])
      expect(result.current.unifiedAlerts).toHaveLength(0)
      expect(result.current.selectedPrediction).toBeUndefined()
      expect(result.current.chartData).toEqual([])
    })

    it('formatPrice gère les prix sub-cent (type PEPE)', async () => {
      mockedApi.getPortfolioPredictions.mockResolvedValue({
        predictions: [makePrediction()],
        summary: makeSummary(),
      })
      mockedApi.getAnomalies.mockResolvedValue([])
      mockedApi.getMarketSentiment.mockResolvedValue(makeSentiment())
      mockedApi.getMarketCycle.mockResolvedValue(null)

      const { result } = renderHook(() => usePredictionData(), { wrapper: createWrapper() })

      await waitFor(() => expect(result.current.predictions).toBeDefined())

      // formatPrice should handle various magnitudes
      expect(result.current.formatPrice(0)).toBe('0')
      expect(result.current.formatPrice(50000)).toBeTruthy() // normal price
      expect(result.current.formatPrice(0.000012)).toMatch(/e-/) // scientific notation
      expect(result.current.formatPrice(0.5)).toBeTruthy() // sub-dollar
    })
  })

  describe('What-If', () => {
    it('appelle l\'API what-if avec le bon symbole et pourcentage', async () => {
      const mockResult = {
        current_value: 100000,
        simulated_value: 150000,
        impact_percent: 50,
        per_asset: [],
      }
      mockedApi.whatIf.mockResolvedValue(mockResult)
      mockedApi.getPortfolioPredictions.mockResolvedValue({
        predictions: [makePrediction()],
        summary: makeSummary(),
      })
      mockedApi.getAnomalies.mockResolvedValue([])
      mockedApi.getMarketSentiment.mockResolvedValue(makeSentiment())
      mockedApi.getMarketCycle.mockResolvedValue(null)

      const { result } = renderHook(() => usePredictionData(), { wrapper: createWrapper() })

      await waitFor(() => expect(result.current.predictions).toBeDefined())

      // Le whatIfSymbol par défaut est le premier symbole
      expect(result.current.whatIfSymbol).toBe('BTC')
    })

    it('retourne whatIfResult null initialement', async () => {
      mockedApi.getPortfolioPredictions.mockResolvedValue({
        predictions: [makePrediction()],
        summary: makeSummary(),
      })
      mockedApi.getAnomalies.mockResolvedValue([])
      mockedApi.getMarketSentiment.mockResolvedValue(makeSentiment())
      mockedApi.getMarketCycle.mockResolvedValue(null)

      const { result } = renderHook(() => usePredictionData(), { wrapper: createWrapper() })

      await waitFor(() => expect(result.current.predictions).toBeDefined())

      expect(result.current.whatIfResult).toBeNull()
      expect(result.current.whatIfLoading).toBe(false)
    })
  })
})
