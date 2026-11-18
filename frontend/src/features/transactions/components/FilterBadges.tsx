import { X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { DATE_OPTIONS, TYPE_OPTIONS } from '../labels'
import type { Filters } from '../useLedger'

function FilterBadge({ label, onRemove }: { label: string | undefined; onRemove: () => void }) {
  return (
    <Badge variant="secondary" className="gap-1">
      {label}
      <X className="h-3 w-3 cursor-pointer" onClick={onRemove} />
    </Badge>
  )
}

export default function FilterBadges({ filters }: { filters: Filters }) {
  const { values, set } = filters
  return (
    <div className="flex flex-wrap gap-2">
      {values.dateRange !== '0' && (
        <FilterBadge label={DATE_OPTIONS.find((d) => d.value === values.dateRange)?.label} onRemove={() => set.dateRange('0')} />
      )}
      {values.type !== 'all' && (
        <FilterBadge label={TYPE_OPTIONS.find((t) => t.value === values.type)?.label} onRemove={() => set.type('all')} />
      )}
      {values.asset !== 'all' && <FilterBadge label={values.asset} onRemove={() => set.asset('all')} />}
      {values.platform !== 'all' && <FilterBadge label={values.platform} onRemove={() => set.platform('all')} />}
      {values.search && <FilterBadge label={`"${values.search}"`} onRemove={() => set.search('')} />}
    </div>
  )
}
