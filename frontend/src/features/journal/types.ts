import type { Schema } from '@/shared/api/client'

export type Note = Schema<'NoteResponse'>
export type NoteSummary = Schema<'NoteSummaryResponse'>
export type Scorecard = Schema<'ScorecardResponse'>
export type ScorecardEntry = Schema<'ScorecardEntry'>
export type NoteCreate = Schema<'NoteCreate'>
export type NoteUpdate = Schema<'NoteUpdate'>
export type AssetOption = Pick<Schema<'AssetResponse'>, 'id' | 'symbol' | 'name'>
