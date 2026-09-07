/**
 * Formes des résultats renvoyés par les endpoints de simulation.
 *
 * Elles vivaient dans `SimulationsPage.tsx`, au-dessus des 2 000 lignes du
 * composant. Les onglets extraits en ont besoin, et un type de réponse d'API
 * n'appartient de toute façon pas à la page qui l'affiche.
 */

// FIRE probabiliste : hypothèses réellement appliquées, échouées par le backend
// (taux en décimal : 0.04 = 4 %). defaults_from trace la provenance des défauts.
export interface FIREAssumptions {
  current_value: number
  monthly_contribution: number
  annual_expenses: number
  withdrawal_rate: number
  annual_return_mean: number
  annual_volatility: number
  inflation: number
  index_contributions: boolean
  years_horizon: number
  n_paths: number
  defaults_from: Record<string, string> | null
}

export interface FIREProbResult {
  prob_by_year: Array<{ year: number; prob: number }>
  prob_at_horizon: number
  fire_year_p10: number | null
  fire_year_p50: number | null
  fire_year_p90: number | null
  final_value_p10: number
  final_value_p50: number
  final_value_p90: number
  fire_number_today: number
  survival_prob_30y: number
  median_path: Array<{ year: number; portfolio_value: number; fire_number: number }>
  n_paths: number
  currency: string
  assumptions: FIREAssumptions
}

export interface ProjectionResult {
  projections: Array<{
    year: number
    nominal_value: number
    real_value: number
    contributions: number
    returns: number
  }>
  final_value: number
  total_contributions: number
  total_returns: number
  real_final_value: number
}

export interface DCAResult {
  total_invested: number
  final_value: number
  average_cost: number
  total_units: number
  return_percent: number
  // Distribution multi-chemins (500 trajectoires simulées côté backend)
  dca_p10: number
  dca_p50: number
  dca_p90: number
  lumpsum_p10: number
  lumpsum_p50: number
  lumpsum_p90: number
  prob_dca_beats_ls: number
  n_paths: number
  projections: Array<{
    period: number
    price: number
    amount_invested: number
    units_bought: number
    total_units: number
    total_invested: number
    current_value: number
    current_value_p10: number
    current_value_p90: number
    lump_sum_value: number
  }>
}

export interface MonteCarloData {
  percentiles: Record<string, number>
  expected_return: number
  prob_positive: number
  prob_loss_10: number
  prob_ruin: number
  simulations: number
  horizon_days: number
}
