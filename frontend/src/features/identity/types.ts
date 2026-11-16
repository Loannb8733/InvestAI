import type { Schema } from '@/shared/api/client'

export type Profile = Schema<'ProfileResponse'>
export type ProfileUpdate = Schema<'ProfileUpdate'>
export type ManagedUser = Schema<'UserResponse'>
export type UserCreate = Schema<'UserCreate'>
export type MfaSetup = Schema<'MfaSetupResponse'>
export type RiskProfile = NonNullable<ProfileUpdate['risk_profile']>

export interface InvestorProfile {
  tmi_rate: number | null
  risk_profile: RiskProfile | null
  monthly_dca_eur: number | null
}
