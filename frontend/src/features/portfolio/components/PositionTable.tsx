import { useState, type KeyboardEvent } from 'react'
import type { PositionGroup, SparklineSeries } from '../types'
import PositionGroupRows from './PositionGroupRows'
import PositionRow, { type RowActions } from './PositionRow'

interface PositionTableProps extends RowActions {
  groups: PositionGroup[]
  sparklines: Record<string, SparklineSeries> | undefined
  onOpenDetail: (group: PositionGroup) => void
}

const COLUMNS = ['Actif', 'Plateforme', 'Quantité', 'PRU', 'Prix actuel', 'Valeur', '+/- Value', 'Risque', '30j', 'Actions']

function headerClass(column: string) {
  if (column === 'Risque') return ' hidden lg:table-cell'
  if (column === '30j') return ' hidden lg:table-cell w-[100px]'
  return ''
}

export default function PositionTable({ groups, sparklines, onOpenDetail, ...actions }: PositionTableProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const toggle = (symbol: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(symbol)) next.delete(symbol)
      else next.add(symbol)
      return next
    })
  }

  const rowProps = (group: PositionGroup) => ({
    role: 'button' as const,
    tabIndex: 0,
    'aria-label': `Voir le détail de ${group.symbol}`,
    onClick: () => onOpenDetail(group),
    onKeyDown: (e: KeyboardEvent<HTMLTableRowElement>) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        onOpenDetail(group)
      }
    },
  })

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b">
            {COLUMNS.map((column) => (
              <th
                key={column}
                scope="col"
                className={`text-center py-2 text-sm font-medium text-muted-foreground${headerClass(column)}`}
                title={column === 'PRU' ? 'Prix de revient (frais inclus)' : undefined}
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {groups.map((group) =>
            group.isMultiPlatform ? (
              <PositionGroupRows
                key={group.symbol}
                group={group}
                sparkline={sparklines?.[group.symbol]}
                rowProps={rowProps(group)}
                expanded={expanded.has(group.symbol)}
                onToggle={() => toggle(group.symbol)}
                {...actions}
              />
            ) : (
              <PositionRow
                key={group.assets[0].id}
                group={group}
                sparkline={sparklines?.[group.symbol]}
                rowProps={rowProps(group)}
                {...actions}
              />
            )
          )}
        </tbody>
      </table>
    </div>
  )
}
