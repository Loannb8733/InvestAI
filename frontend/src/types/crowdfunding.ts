export type RepaymentType = 'in_fine' | 'amortizable'
export type ProjectStatus = 'funding' | 'active' | 'completed' | 'delayed' | 'defaulted'

/** Labels FR partagés (badges de statut) — source unique pour toutes les pages crowdfunding. */
export const STATUS_LABELS: Record<ProjectStatus, string> = {
  funding: 'En cours de levée',
  active: 'Actif',
  completed: 'Terminé',
  delayed: 'En retard',
  defaulted: 'Défaut',
}

/** Classes de couleur partagées pour les badges de statut. */
export const STATUS_COLORS: Record<ProjectStatus, string> = {
  funding: 'bg-warning/10 text-warning',
  active: 'bg-gain/10 text-gain',
  completed: 'bg-accent/10 text-accent',
  delayed: 'bg-warning/10 text-warning',
  defaulted: 'bg-loss/10 text-loss',
}

export interface ProjectDocument {
  id: string
  project_id: string
  file_name: string
  file_size: number
  audit_id: string | null
  created_at: string
}

export type PaymentType = 'interest' | 'capital' | 'both'

export interface CrowdfundingRepayment {
  id: string
  project_id: string
  payment_date: string
  amount: number
  payment_type: PaymentType
  interest_amount: number | null
  capital_amount: number | null
  tax_amount: number | null
  notes: string | null
  created_at: string
}

export type ScheduleStatus = 'paid' | 'pending' | 'overdue'
export type InterestFrequency = 'at_maturity' | 'monthly' | 'quarterly' | 'semi_annual' | 'annual'

export interface PaymentScheduleEntry {
  id: string
  project_id: string
  due_date: string
  expected_capital: number
  expected_interest: number
  is_completed: boolean
  completed_at: string | null
  repayment_id: string | null
  status: ScheduleStatus
}

export interface CrowdfundingProject {
  id: string
  asset_id: string
  platform: string
  project_name: string | null
  description: string | null
  project_url: string | null
  invested_amount: number
  annual_rate: number
  duration_months: number
  repayment_type: RepaymentType
  interest_frequency: InterestFrequency | null
  tax_rate: number
  delay_months: number
  start_date: string | null
  estimated_end_date: string | null
  actual_end_date: string | null
  status: ProjectStatus
  total_received: number
  created_at: string
  updated_at: string
  /** Intérêts projetés NETS de flat tax. */
  projected_total_interest: number | null
  /** Intérêts projetés BRUTS de fiscalité (invested × rate × months/12) — base homogène face à interest_earned (brut). */
  projected_interest_gross: number | null
  /** Intérêts réellement encaissés à date (bruts, avant prélèvements). */
  interest_earned: number | null
  progress_percent: number | null
  documents: ProjectDocument[]
  repayments: CrowdfundingRepayment[]
  schedule: PaymentScheduleEntry[]
}

export interface CrowdfundingCreateData {
  portfolio_id: string
  platform: string
  project_name: string
  description?: string
  project_url?: string
  invested_amount: number
  annual_rate: number
  duration_months: number
  repayment_type: RepaymentType
  interest_frequency?: InterestFrequency
  tax_rate?: number
  delay_months?: number
  start_date?: string
  estimated_end_date?: string
  status?: ProjectStatus
}

export interface CrowdfundingUpdateData {
  project_name?: string
  description?: string
  project_url?: string
  platform?: string
  annual_rate?: number
  duration_months?: number
  repayment_type?: RepaymentType
  interest_frequency?: InterestFrequency
  tax_rate?: number
  delay_months?: number
  start_date?: string
  estimated_end_date?: string
  actual_end_date?: string
  status?: ProjectStatus
  total_received?: number
}

export interface CrowdfundingDashboard {
  total_invested: number
  total_received: number
  /** Intérêts réellement encaissés (seul vrai P&L — le capital remboursé n'est pas un gain). */
  total_interest_received: number
  /** Capital déjà remboursé (retour de principal, pas un gain). */
  total_capital_repaid: number
  /** Capital restant dû des projets sains — la valeur réelle de la poche. */
  capital_outstanding: number
  /** Principal exposé sur projets en défaut (provisionné en perte). */
  defaulted_outstanding: number
  projected_annual_interest: number
  weighted_average_rate: number
  active_count: number
  completed_count: number
  delayed_count: number
  defaulted_count: number
  funding_count: number
  next_maturity: string | null
  /** Montants investis par plateforme (coût historique). */
  platform_breakdown: Record<string, number>
  /** Exposition par plateforme au capital restant dû (projets en défaut exclus). Optionnel pour compat backend. */
  platform_breakdown_outstanding?: Record<string, number>
  projects: CrowdfundingProject[]
}

export interface GuaranteeInfo {
  type: string
  rank: string | null
  description: string
  strength: 'forte' | 'moyenne' | 'faible'
}

export interface InvestmentSimulation {
  investment_amount: number
  duration_months: number
  tri_percent: number
  gross_interest: number
  tax_amount: number
  net_interest: number
  monthly_gross_return: number
  total_at_end: number
  roi_net_percent: number
}

export interface ProjectAudit {
  id: string
  project_id: string | null
  file_names: string[]
  document_type: string | null
  project_name: string | null
  operator: string | null
  location: string | null
  tri: number | null
  duration_min: number | null
  duration_max: number | null
  collection_amount: number | null
  margin_percent: number | null
  ltv: number | null
  ltc: number | null
  pre_sales_percent: number | null
  equity_contribution: number | null
  guarantees: GuaranteeInfo[]
  admin_status: string | null
  score_operator: number | null
  score_location: number | null
  score_guarantees: number | null
  score_risk_return: number | null
  score_admin: number | null
  risk_score: number | null
  points_forts: string[]
  points_vigilance: string[]
  red_flags: string[]
  verdict: 'INVESTIR' | 'VIGILANCE' | 'NE_PAS_INVESTIR'
  suggested_investment: number | null
  diversification_impact: string | null
  correlation_score: number | null
  portfolio_concentration: Record<string, number> | null
  investment_simulation: InvestmentSimulation | null
  created_at: string
}

export interface StressTestCashflow {
  date: string
  capital: number
  interest: number
  total: number
  is_delayed: boolean
}

export interface StressTestResult {
  project_id: string
  delay_months: number
  base_irr: number | null
  stressed_irr: number | null
  irr_delta: number | null
  cashflows: StressTestCashflow[]
}

export interface CrowdfundingPerformanceItem {
  id: string
  project_name: string | null
  platform: string
  status: ProjectStatus
  invested_amount: number
  annual_rate: number
  duration_months: number
  repayment_type: RepaymentType
  /** Intérêts projetés NETS de flat tax. */
  projected_total_interest: number
  /** Intérêts projetés BRUTS de fiscalité — à comparer à interest_earned (brut). */
  projected_interest_gross: number
  /** Total reçu (brut, capital + intérêts) — ne pas comparer aux intérêts projetés. */
  total_received: number
  /** Intérêts réellement encaissés (bruts). */
  interest_earned: number
  elapsed_months: number
  progress_percent: number
  on_track: boolean
  start_date: string | null
  estimated_end_date: string | null
}
