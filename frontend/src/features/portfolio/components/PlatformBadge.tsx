import { useState } from 'react'
import { Building2, ChevronDown, Shield } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ALL_PLATFORMS, isColdWallet } from '@/lib/platforms'
import type { Position } from '../types'

interface PlatformBadgeProps {
  asset: Position
  onChange: (assetId: string, exchange: string | null) => void
}

function badgeClass(exchange: string | null) {
  if (!exchange) return 'bg-muted/50 text-muted-foreground'
  return isColdWallet(exchange) ? 'bg-accent/10 text-accent' : 'bg-muted text-muted-foreground'
}

export default function PlatformBadge({ asset, onChange }: PlatformBadgeProps) {
  const [open, setOpen] = useState(false)
  const choose = (exchange: string | null) => {
    onChange(asset.id, exchange)
    setOpen(false)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          className={`text-xs px-2 py-0.5 rounded inline-flex items-center gap-1 cursor-pointer hover:opacity-80 transition-opacity ${badgeClass(asset.exchange)}`}
        >
          {asset.exchange && isColdWallet(asset.exchange) && <Shield className="h-3 w-3" />}
          {asset.exchange || 'Non assigné'}
          <ChevronDown className="h-3 w-3 opacity-50" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-44 p-1" align="center">
        <div className="max-h-52 overflow-y-auto">
          {ALL_PLATFORMS.map((platform) => (
            <button
              key={platform}
              className={`w-full text-left text-xs px-2 py-1.5 rounded flex items-center gap-2 hover:bg-muted transition-colors ${
                asset.exchange === platform ? 'bg-muted font-medium' : ''
              }`}
              onClick={() => choose(platform)}
            >
              {isColdWallet(platform) && <Shield className="h-3 w-3 text-accent shrink-0" />}
              {!isColdWallet(platform) && <Building2 className="h-3 w-3 text-muted-foreground shrink-0" />}
              {platform}
            </button>
          ))}
          {asset.exchange && (
            <button
              className="w-full text-left text-xs px-2 py-1.5 rounded text-muted-foreground hover:bg-muted transition-colors"
              onClick={() => choose(null)}
            >
              Retirer la plateforme
            </button>
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}
