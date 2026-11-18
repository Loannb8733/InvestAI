import { useMemo, useState } from 'react'
import { Check, ChevronsUpDown, Plus, Shield } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { COLD_WALLETS, EXCHANGES, getTrustColor, getTrustLabel, getTrustScore } from '@/lib/platforms'
import { cn } from '@/lib/utils'
import { useUserPlatforms } from '../hooks'
import NewPlatform from './NewPlatform'

interface PlatformSelectProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  showTrustBadge?: boolean
}

type Group = 'exchange' | 'wallet' | 'user'

function TrustBadge({ platform }: { platform: string }) {
  const score = getTrustScore(platform)
  const color = getTrustColor(score)
  return (
    <span className="inline-flex items-center gap-0.5 text-[10px] font-medium" title={`${getTrustLabel(score)} (${score}/10)`}>
      <Shield className="h-3 w-3" style={{ color }} fill={color} fillOpacity={0.2} />
      <span style={{ color }}>{score}</span>
    </span>
  )
}

export default function PlatformSelect({
  value,
  onChange,
  placeholder = 'Sélectionner une plateforme',
  showTrustBadge = true,
}: PlatformSelectProps) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [creating, setCreating] = useState(false)
  const { data } = useUserPlatforms()

  const allPlatforms = useMemo(() => {
    const seen = new Map<string, { name: string; group: Group }>()
    for (const p of EXCHANGES) seen.set(p.toLowerCase(), { name: p, group: 'exchange' })
    for (const p of COLD_WALLETS) seen.set(p.toLowerCase(), { name: p, group: 'wallet' })
    for (const p of data?.platforms ?? []) {
      if (!seen.has(p.toLowerCase())) seen.set(p.toLowerCase(), { name: p, group: 'user' })
    }
    return Array.from(seen.values())
  }, [data?.platforms])

  const inGroup = (group: Group) => allPlatforms.filter((p) => p.group === group)
  const custom = inGroup('user')

  const select = (name: string) => {
    onChange(name)
    setOpen(false)
    setSearch('')
  }

  const item = (p: { name: string }) => (
    <CommandItem key={p.name} value={p.name} onSelect={() => select(p.name)}>
      <Check className={cn('mr-2 h-4 w-4', value === p.name ? 'opacity-100' : 'opacity-0')} />
      <span className="flex-1">{p.name}</span>
      {showTrustBadge && <TrustBadge platform={p.name} />}
    </CommandItem>
  )

  if (creating) {
    return (
      <NewPlatform
        taken={(name) => allPlatforms.some((p) => p.name.toLowerCase() === name.toLowerCase())}
        onCreate={(name) => {
          onChange(name)
          setCreating(false)
        }}
        onCancel={() => setCreating(false)}
      />
    )
  }

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button variant="outline" role="combobox" aria-expanded={open} aria-label={placeholder} className="w-full justify-between font-normal">
              <span className={cn('flex items-center gap-1.5', !value && 'text-muted-foreground')}>
                {value ? (
                  <>
                    {value}
                    {showTrustBadge && <TrustBadge platform={value} />}
                  </>
                ) : (
                  placeholder
                )}
              </span>
              <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-(--radix-popover-trigger-width) p-0" align="start">
            <Command shouldFilter={true}>
              <CommandInput placeholder="Rechercher..." value={search} onValueChange={setSearch} />
              <CommandList>
                <CommandEmpty>Aucune plateforme trouvée</CommandEmpty>
                <CommandGroup heading="Exchanges">{inGroup('exchange').map(item)}</CommandGroup>
                <CommandGroup heading="Cold Wallets">{inGroup('wallet').map(item)}</CommandGroup>
                {custom.length > 0 && <CommandGroup heading="Mes plateformes">{custom.map(item)}</CommandGroup>}
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-auto py-1.5 px-2 text-xs text-primary shrink-0"
          onClick={() => setCreating(true)}
        >
          <Plus className="h-3 w-3 mr-1" />
          Nouvelle
        </Button>
      </div>
    </div>
  )
}
