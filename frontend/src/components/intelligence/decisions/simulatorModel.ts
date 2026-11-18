export type TemplateKind = 'dca' | 'vca' | 'profit_taking' | 'rebalance'
export type Frequency = 'weekly' | 'biweekly' | 'monthly' | 'quarterly'

export const TEMPLATE_OPTIONS: { value: TemplateKind; label: string; hint: string }[] = [
  { value: 'dca', label: 'Achat périodique (DCA)', hint: 'Un budget fixe à chaque échéance, réparti entre les actifs que vous choisissez.' },
  { value: 'vca', label: 'Value averaging (VCA)', hint: 'La valeur visée de la ligne augmente d’un montant fixe ; on investit l’écart à chaque échéance.' },
  { value: 'profit_taking', label: 'Prise de profits par paliers', hint: 'Vendre une part de la quantité que vous indiquez à chaque seuil de prix que vous fixez.' },
  { value: 'rebalance', label: 'Rééquilibrage', hint: 'Revenir à l’allocation cible que vous choisissez, à partir des valeurs que vous saisissez.' },
]

export const FREQUENCY_OPTIONS: { value: Frequency; label: string }[] = [
  { value: 'weekly', label: 'Chaque semaine' },
  { value: 'biweekly', label: 'Toutes les deux semaines' },
  { value: 'monthly', label: 'Chaque mois' },
  { value: 'quarterly', label: 'Chaque trimestre' },
]

export interface Row {
  symbol: string
  a: string
  b: string
}

export interface SimulatorForm {
  template: TemplateKind
  frequency: Frequency
  periods: string
  startDate: string
  amount: string
  maxPerPeriod: string
  allowSell: boolean
  symbol: string
  quantity: string
  contribution: string
  threshold: string
  rows: Row[]
  backtestStart: string
}

export const emptyRow = (): Row => ({ symbol: '', a: '', b: '' })

export function emptyForm(today: string): SimulatorForm {
  return {
    template: 'dca',
    frequency: 'monthly',
    periods: '',
    startDate: today,
    amount: '',
    maxPerPeriod: '',
    allowSell: false,
    symbol: '',
    quantity: '',
    contribution: '',
    threshold: '',
    rows: [emptyRow()],
    backtestStart: '',
  }
}

export interface ScheduleLine {
  date: string | null
  action: 'BUY' | 'SELL' | 'REVIEW'
  symbol: string | null
  amount: number | null
  quantity: number | null
  trigger_price: number | null
  target_value: number | null
  note: string
}

export interface Backtest {
  available: boolean
  reason: string | null
  start_date: string | null
  end_date: string | null
  events_planned: number
  events_simulated: number
  missing_prices: number
  invested_eur: number | null
  withdrawn_eur: number | null
  final_value_eur: number | null
  pnl_eur: number | null
  pnl_pct: number | null
  benchmark_label: string | null
  benchmark_value_eur: number | null
  note: string
}

export interface Simulation {
  template: TemplateKind
  rule_summary: string
  schedule: ScheduleLine[]
  total_buy_eur: number
  total_sell_eur: number
  has_amounts_at_execution: boolean
  backtest: Backtest | null
  disclaimer: string
}

const num = (value: string) => Number(value.replace(',', '.'))
const symbolOf = (value: string) => value.trim().toUpperCase()
const filled = (rows: Row[]) => rows.filter((r) => r.symbol.trim())

function cadence(form: SimulatorForm) {
  return { frequency: form.frequency, periods: num(form.periods), start_date: form.startDate }
}

export function toParams(form: SimulatorForm): Record<string, unknown> {
  switch (form.template) {
    case 'dca':
      return {
        template: 'dca',
        assets: filled(form.rows).map((r) => ({ symbol: symbolOf(r.symbol), weight_pct: num(r.a) })),
        amount_per_period: num(form.amount),
        ...cadence(form),
      }
    case 'vca':
      return {
        template: 'vca',
        symbol: symbolOf(form.symbol),
        target_increment: num(form.amount),
        max_per_period: form.maxPerPeriod.trim() ? num(form.maxPerPeriod) : null,
        allow_sell: form.allowSell,
        ...cadence(form),
      }
    case 'profit_taking':
      return {
        template: 'profit_taking',
        symbol: symbolOf(form.symbol),
        quantity: num(form.quantity),
        tiers: form.rows.filter((r) => r.a.trim()).map((r) => ({ price: num(r.a), sell_pct: num(r.b) })),
      }
    case 'rebalance':
      return {
        template: 'rebalance',
        lines: filled(form.rows).map((r) => ({
          symbol: symbolOf(r.symbol),
          target_pct: num(r.a),
          current_value: r.b.trim() ? num(r.b) : 0,
        })),
        contribution: form.contribution.trim() ? num(form.contribution) : 0,
        threshold_pct: form.threshold.trim() ? num(form.threshold) : 0,
        ...cadence(form),
      }
  }
}

export function apiError(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string }
    return (first.msg ?? 'Paramètres invalides').replace(/^Value error, /, '')
  }
  return 'Paramètres invalides : vérifiez les champs.'
}

export const ACTION_LABELS: Record<string, string> = { BUY: 'Achat', SELL: 'Vente', REVIEW: 'Revue' }
