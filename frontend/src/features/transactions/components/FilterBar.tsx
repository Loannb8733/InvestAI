import { useMemo, type ReactNode } from 'react'
import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { DATE_OPTIONS, TYPE_OPTIONS } from '../labels'
import { assetChoices, platformChoices } from '../ledger'
import type { Choice, Transaction } from '../types'
import type { Filters } from '../useLedger'

interface ChoiceSelectProps {
  value: string
  onChange: (value: string) => void
  width: string
  placeholder?: string
  allLabel?: string
  options: { value: string; label: ReactNode }[]
}

function ChoiceSelect({ value, onChange, width, placeholder, allLabel, options }: ChoiceSelectProps) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className={`${width} h-9`}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {allLabel && <SelectItem value="all">{allLabel}</SelectItem>}
        {options.map((opt) => (
          <SelectItem key={opt.value} value={opt.value}>
            {opt.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

const counted = (choices: Choice[]) =>
  choices.map((c) => ({
    value: c.value,
    label: (
      <>
        {c.value} ({c.count})
      </>
    ),
  }))

interface FilterBarProps {
  portfolios: { id: string; name: string }[]
  filters: Filters
  transactions: Transaction[]
}

export default function FilterBar({ portfolios, filters, transactions }: FilterBarProps) {
  const { values, set } = filters
  const assets = useMemo(() => assetChoices(transactions, values.asset), [transactions, values.asset])
  const platforms = useMemo(() => platformChoices(transactions, values.platform), [transactions, values.platform])

  return (
    <div className="flex flex-wrap items-center gap-2">
      <ChoiceSelect
        value={values.portfolio}
        onChange={set.portfolio}
        width="w-40"
        placeholder="Portefeuille"
        allLabel="Tous les portefeuilles"
        options={portfolios.map((p) => ({ value: p.id, label: p.name }))}
      />
      <ChoiceSelect value={values.dateRange} onChange={set.dateRange} width="w-36" options={DATE_OPTIONS} />
      <ChoiceSelect value={values.type} onChange={set.type} width="w-36" options={TYPE_OPTIONS} />
      {assets.length > 0 && (
        <ChoiceSelect
          value={values.asset}
          onChange={set.asset}
          width="w-32"
          placeholder="Actif"
          allLabel="Tous les actifs"
          options={counted(assets)}
        />
      )}
      {platforms.length > 1 && (
        <ChoiceSelect
          value={values.platform}
          onChange={set.platform}
          width="w-32"
          placeholder="Plateforme"
          allLabel="Toutes"
          options={counted(platforms)}
        />
      )}
      {filters.active > 0 && (
        <Button variant="ghost" size="sm" onClick={filters.clear} className="h-9 px-2">
          <X className="h-4 w-4 mr-1" />
          Effacer ({filters.active})
        </Button>
      )}
    </div>
  )
}
