export type RepaymentType = 'in_fine' | 'amortizable'
export type ProjectStatus = 'funding' | 'active' | 'completed' | 'delayed' | 'defaulted'

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
  start_date: string | null
  estimated_end_date: string | null
  actual_end_date: string | null
  status: ProjectStatus
  total_received: number
  created_at: string
  updated_at: string
  projected_total_interest: number | null
  interest_earned: number | null
  progress_percent: number | null
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
  start_date?: string
  estimated_end_date?: string
  actual_end_date?: string
  status?: ProjectStatus
  total_received?: number
}

export interface CrowdfundingDashboard {
  total_invested: number
  total_received: number
  projected_annual_interest: number
  weighted_average_rate: number
  active_count: number
  completed_count: number
  delayed_count: number
  defaulted_count: number
  funding_count: number
  next_maturity: string | null
  platform_breakdown: Record<string, number>
  projects: CrowdfundingProject[]
}

export interface GuaranteeInfo {
  type: string
  rank: string | null
  description: string
  strength: 'forte' | 'moyenne' | 'faible'
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
  created_at: string
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
  projected_total_interest: number
  total_received: number
  interest_earned: number
  elapsed_months: number
  progress_percent: number
  on_track: boolean
  start_date: string | null
  estimated_end_date: string | null
}
