import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import type { TypeButton } from '../typeButtons'
import type { TransactionType } from '../types'

interface TypeToggleProps {
  buttons: TypeButton[]
  value: string
  onChange: (type: TransactionType) => void
}

export default function TypeToggle({ buttons, value, onChange }: TypeToggleProps) {
  return (
    <div className="space-y-2">
      <Label className="text-xs text-muted-foreground uppercase tracking-wider">Type de transaction</Label>
      <div className="grid grid-cols-4 gap-1.5">
        {buttons.map((type) => {
          const Icon = type.icon
          const isActive = value === type.value
          return (
            <button
              key={type.value}
              type="button"
              aria-label={type.label}
              aria-pressed={isActive}
              onClick={() => onChange(type.value)}
              className={cn(
                'flex flex-col items-center gap-1 rounded-lg border px-2 py-2 text-[11px] font-medium transition-all duration-150',
                isActive ? type.activeBg : `${type.bg} hover:opacity-80 opacity-60`
              )}
            >
              <Icon className={cn('h-4 w-4', type.color)} />
              <span className={cn('truncate w-full text-center', isActive ? 'text-foreground' : 'text-muted-foreground')}>
                {type.shortLabel}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
