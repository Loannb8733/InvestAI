import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, within } from '@testing-library/react'
import { http } from '@/shared/api/http'
import { createFakeServer, ok, polyfillRadixPointer, visibleText } from '@/test/fakeServer'
import { chooseOption, renderWithQuery, settle } from '@/test/render'
import StrategiesSection from './StrategiesSection'

vi.mock('@/hooks/use-toast', () => {
  const toast = () => {}
  return { toast, useToast: () => ({ toast }) }
})

const server = createFakeServer()
const { calls } = server
const NOW = '2026-10-17T12:00:00Z'

const action = (id: string, extra: Record<string, unknown>) => ({
  id,
  strategy_id: 's',
  symbol: 'BTC',
  currency: 'EUR',
  reason: null,
  status: 'PENDING',
  scheduled_at: null,
  executed_at: null,
  created_at: NOW,
  ...extra,
})

const LEGACY = {
  id: 'legacy-1',
  user_id: 'u1',
  name: 'Conviction buy — BTC',
  description: null,
  source: 'AI',
  status: 'PROPOSED',
  params: { type: 'conviction_buy', available_liquidity: 3000, total_proposed_amount: 120, risk_level: 4, performance_potential: 4 },
  rule_summary: null,
  ai_reasoning: 'Peur extrême : acheter fort.',
  market_regime: 'bottom',
  confidence: 0.2,
  actions: [action('a-legacy', { action: 'ACHAT FORT', amount: 120, reason: 'Alpha 70/100 — 4 % de vos liquidités' })],
  created_at: NOW,
  updated_at: NOW,
}

const PROGRAMMED = {
  ...LEGACY,
  id: 'vca-1',
  name: 'VCA SOL',
  source: 'USER',
  status: 'ACTIVE',
  params: { template: 'vca' },
  rule_summary: 'Value averaging sur SOL : la valeur visée de la ligne augmente de 40,00 € chaque semaine.',
  ai_reasoning: null,
  market_regime: null,
  confidence: null,
  actions: [action('a-vca', { action: 'BUY', symbol: 'SOL', amount: null, scheduled_at: '2026-11-08T00:00:00Z' })],
}

const SIMULATION = {
  template: 'dca',
  rule_summary: 'Achat périodique : 50,00 € chaque mois, 2 échéances à partir du 01/11/2026, répartis BTC 100 %.',
  schedule: [
    { date: '2026-11-01', action: 'BUY', symbol: 'BTC', amount: 50, quantity: null, trigger_price: null, target_value: null, note: 'Échéance 1/2 : 50,00 € sur BTC' },
    { date: '2026-12-01', action: 'BUY', symbol: 'BTC', amount: 50, quantity: null, trigger_price: null, target_value: null, note: 'Échéance 2/2 : 50,00 € sur BTC' },
  ],
  total_buy_eur: 100,
  total_sell_eur: 0,
  has_amounts_at_execution: false,
  backtest: {
    available: true, reason: null, start_date: '2026-01-15', end_date: '2026-10-17', events_planned: 2, events_simulated: 2,
    missing_prices: 0, invested_eur: 100, withdrawn_eur: 0, final_value_eur: 112, pnl_eur: 12, pnl_pct: 12,
    benchmark_label: null, benchmark_value_eur: null, note: 'Simulation passée, sans valeur prédictive.',
  },
  disclaimer: 'Simulation calculée uniquement à partir des paramètres que vous avez saisis. Pas un conseil en investissement.',
}

const writes = () => calls.filter((c) => c.method !== 'GET')
const input = (label: string) => screen.getByLabelText(label) as HTMLInputElement
const type = (label: string, value: string) => fireEvent.change(input(label), { target: { value } })

async function open() {
  renderWithQuery(<StrategiesSection />)
  await screen.findByText('VCA SOL')
}

beforeAll(() => {
  polyfillRadixPointer()
  http.defaults.adapter = server.adapter
})

beforeEach(() => {
  server.reset({
    'GET /strategies': ok([PROGRAMMED, LEGACY]),
    'PATCH /strategies/legacy-1/reject': ok({ ...LEGACY, status: 'REJECTED' }),
    'POST /strategies/simulate': ok(SIMULATION),
    'POST /strategies/from-template': () => ({ status: 201, data: { ...PROGRAMMED, id: 'new' } }),
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Stratégies programmées', () => {
  it('ne propose plus aucune stratégie automatique', async () => {
    await open()
    const text = visibleText().join(' ')
    expect(text).toContain('Stratégies programmées')
    expect(text).not.toMatch(/Stratégies IA|Analyser mon portefeuille|Propositions IA|Munitions|liquidités/)
    expect(screen.queryByRole('button', { name: /Accepter/ })).toBeNull()
  })

  it('affiche les anciennes suggestions sans leur analyse, et permet de les archiver', async () => {
    await open()
    expect(screen.getByText('Anciennes suggestions automatiques')).toBeTruthy()
    expect(screen.getByText('Ancienne suggestion')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Déplier le détail de Conviction buy — BTC' }))
    expect(screen.getByText('ACHAT FORT')).toBeTruthy()
    expect(visibleText().join(' ')).not.toContain('Peur extrême')
    expect(visibleText().join(' ')).not.toContain('bottom')
    fireEvent.click(screen.getByRole('button', { name: 'Archiver la stratégie Conviction buy — BTC' }))
    await settle(() => writes().length === 1)
    expect(writes()).toEqual([{ method: 'PATCH', url: '/strategies/legacy-1/reject' }])
  })

  it('décrit la règle programmée et laisse saisir un montant calculé à l’échéance', async () => {
    await open()
    expect(screen.getByText(PROGRAMMED.rule_summary)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Déplier le détail de VCA SOL' }))
    expect(screen.getByText('Achat')).toBeTruthy()
    expect(screen.getByText(/Prévue le/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Saisir le montant' })).toBeTruthy()
  })

  it('simule puis enregistre une règle à partir des seuls paramètres saisis', async () => {
    await open()
    fireEvent.click(screen.getByRole('button', { name: 'Simuler une stratégie' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Simulateur de stratégies')).toBeTruthy()
    expect(input('Budget par échéance (€)').value).toBe('')
    expect(input('Nombre d’échéances').value).toBe('')
    expect(input('Part (%) 1').value).toBe('')

    chooseOption(within(dialog).getByRole('combobox', { name: 'Fréquence' }), 'Chaque mois')
    type('Actif 1', 'btc')
    type('Part (%) 1', '100')
    type('Budget par échéance (€)', '50')
    type('Nombre d’échéances', '2')
    type('Première échéance', '2026-11-01')
    type('Simuler sur l’historique depuis (facultatif)', '2026-01-15')
    fireEvent.click(within(dialog).getByRole('button', { name: /Calculer l’aperçu/ }))

    await screen.findByText(SIMULATION.rule_summary)
    const params = {
      template: 'dca',
      assets: [{ symbol: 'BTC', weight_pct: 100 }],
      amount_per_period: 50,
      frequency: 'monthly',
      periods: 2,
      start_date: '2026-11-01',
    }
    expect(writes()).toEqual([{ method: 'POST', url: '/strategies/simulate', body: { params, backtest_start: '2026-01-15' } }])
    expect(screen.getByText(SIMULATION.disclaimer)).toBeTruthy()
    expect(screen.getByText(/Si cette règle avait été appliquée/)).toBeTruthy()
    expect(screen.getByText(SIMULATION.backtest.note)).toBeTruthy()

    type('Nom de la stratégie', 'DCA BTC')
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer la stratégie' }))
    await settle(() => writes().length === 2)
    expect(writes()[1]).toEqual({ method: 'POST', url: '/strategies/from-template', body: { name: 'DCA BTC', params } })
  })

  it('montre l’erreur de validation renvoyée par le serveur', async () => {
    server.routes['POST /strategies/simulate'] = () => ({
      status: 422,
      data: { detail: [{ msg: 'Value error, Les pourcentages doivent totaliser 100 % (actuellement 70 %)' }] },
    })
    await open()
    fireEvent.click(screen.getByRole('button', { name: 'Simuler une stratégie' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: /Calculer l’aperçu/ }))
    expect((await screen.findByRole('alert')).textContent).toBe('Les pourcentages doivent totaliser 100 % (actuellement 70 %)')
  })
})
