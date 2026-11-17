import type { ReactNode } from 'react'
import { Building2, Shield } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { isColdWallet } from '@/lib/platforms'
import { UNASSIGNED } from '../grouping'

interface PlatformFilterCardProps {
  platform: string
  filter: string | null
  onFilterChange: (platform: string | null) => void
  children: ReactNode
}

function stateClass(isActive: boolean, filter: string | null, isWallet: boolean) {
  if (isActive) return 'ring-2 ring-primary border-primary'
  if (filter) return 'opacity-50 hover:opacity-75'
  return isWallet ? 'border-accent/20 hover:border-accent/40' : 'hover:bg-muted/50'
}

export default function PlatformFilterCard({ platform, filter, onFilterChange, children }: PlatformFilterCardProps) {
  const isWallet = isColdWallet(platform)
  const isActive = filter === platform
  return (
    <Card
      elevation="interactive"
      className={`cursor-pointer transition-all ${stateClass(isActive, filter, isWallet)}`}
      onClick={() => onFilterChange(isActive ? null : platform)}
    >
      <CardContent className="py-3 px-4">
        <div className="flex items-center gap-2 mb-1.5">
          {isWallet ? (
            <Shield className="h-4 w-4 text-accent shrink-0" />
          ) : platform === UNASSIGNED ? null : (
            <Building2 className="h-4 w-4 text-muted-foreground shrink-0" />
          )}
          <span className={`text-sm font-medium truncate ${isWallet ? 'text-accent' : ''}`}>{platform}</span>
        </div>
        {children}
      </CardContent>
    </Card>
  )
}
