import StatCard from '@/components/ui/stat-card'
import SpotlightGroup from '@/components/ui/spotlight-group'
import { fmtCount } from '../format'
import type { NoteSummary } from '../types'

export default function NoteSummaryCards({ summary }: { summary: NoteSummary }) {
  return (
    <SpotlightGroup className="grid gap-4 md:grid-cols-3">
      <StatCard className="spot-card" label="Total notes" value={summary.total_notes} format={fmtCount} />
      <StatCard className="spot-card" label="Ce mois-ci" value={summary.notes_this_month} format={fmtCount} />
      <StatCard className="spot-card" label="Tags utilisés" value={summary.unique_tags.length} format={fmtCount} />
    </SpotlightGroup>
  )
}
