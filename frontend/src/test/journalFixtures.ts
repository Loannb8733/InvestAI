import { ok, type Handler } from './fakeServer'

export const NOTE_BTC = {
  id: 'n1',
  title: 'Accumuler le BTC',
  content: 'Achat progressif sous 60 000.',
  tags: 'crypto, long terme',
  asset_id: 'a1',
  asset_symbol: 'BTC',
  asset_name: 'Bitcoin',
  transaction_ids: null,
  attachments: null,
  sentiment: 'bullish',
  created_at: '2026-03-04T09:15:00Z',
  updated_at: '2026-03-04T09:15:00Z',
}

export const NOTE_PLAIN = {
  id: 'n2',
  title: 'Revue trimestrielle',
  content: null,
  tags: null,
  asset_id: null,
  asset_symbol: null,
  asset_name: null,
  transaction_ids: null,
  attachments: null,
  sentiment: null,
  created_at: '2026-01-15T18:00:00Z',
  updated_at: '2026-01-15T18:00:00Z',
}

export const SUMMARY = { total_notes: 2, notes_this_month: 1, unique_tags: ['crypto', 'long terme'] }

export const ASSETS = [
  { id: 'a1', symbol: 'BTC', name: 'Bitcoin' },
  { id: 'a2', symbol: 'ETH', name: null },
]

export const SCORECARD = {
  entries: [
    {
      note_id: 'n1',
      title: 'Accumuler le BTC',
      symbol: 'BTC',
      sentiment: 'bullish',
      note_date: '2026-03-04T09:15:00Z',
      perf_30d: 4.25,
      perf_90d: -3.5,
      verdict_30d: 'correct',
      verdict_90d: 'incorrect',
    },
    {
      note_id: 'n3',
      title: 'Prudence sur ETH',
      symbol: 'ETH',
      sentiment: 'neutral',
      note_date: '2026-05-20T10:00:00Z',
      perf_30d: 0,
      perf_90d: null,
      verdict_30d: 'correct',
      verdict_90d: 'pending',
    },
  ],
  summary: {
    total_scored: 2,
    unscorable: 1,
    hit_rate_30d: 100,
    hit_rate_90d: 0,
    by_sentiment: { bullish: { n: 1, hit_rate: 50 }, neutral: { n: 1, hit_rate: null } },
  },
}

export function journalRoutes(): Record<string, Handler> {
  return {
    'GET /notes': ok([NOTE_BTC, NOTE_PLAIN]),
    'GET /notes/summary': ok(SUMMARY),
    'GET /assets': ok(ASSETS),
    'GET /notes/scorecard': ok(SCORECARD),
    'POST /notes': (config) => ({ status: 201, data: { ...NOTE_PLAIN, id: 'n9', ...JSON.parse(String(config.data)) } }),
    'PATCH /notes/n1': (config) => ({ status: 200, data: { ...NOTE_BTC, ...JSON.parse(String(config.data)) } }),
    'DELETE /notes/n1': () => ({ status: 204 }),
  }
}
