import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Check, ChevronsUpDown, Plus, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { EXCHANGES, COLD_WALLETS } from '@/lib/platforms'
import { transactionsApi } from '@/services/api'

interface PlatformSelectProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
}

const MAX_LENGTH = 50

export function PlatformSelect({ value, onChange, placeholder = 'Sélectionner une plateforme' }: PlatformSelectProps) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [newPlatformName, setNewPlatformName] = useState('')

  const { data } = useQuery({
    queryKey: ['user-platforms'],
    queryFn: () => transactionsApi.getPlatforms(),
    staleTime: 60_000,
  })

  const userPlatforms = data?.platforms ?? []

  const allPlatforms = useMemo(() => {
    const seen = new Map<string, { name: string; group: 'exchange' | 'wallet' | 'user' }>()

    for (const p of EXCHANGES) {
      seen.set(p.toLowerCase(), { name: p, group: 'exchange' })
    }
    for (const p of COLD_WALLETS) {
      seen.set(p.toLowerCase(), { name: p, group: 'wallet' })
    }
    for (const p of userPlatforms) {
      const key = p.toLowerCase()
      if (!seen.has(key)) {
        seen.set(key, { name: p, group: 'user' })
      }
    }

    return Array.from(seen.values())
  }, [userPlatforms])

  const exchanges = allPlatforms.filter((p) => p.group === 'exchange')
  const wallets = allPlatforms.filter((p) => p.group === 'wallet')
  const custom = allPlatforms.filter((p) => p.group === 'user')

  const handleSelect = (name: string) => {
    onChange(name)
    setOpen(false)
    setSearch('')
  }

  const trimmedNew = newPlatformName.trim()
  const canCreate =
    trimmedNew.length > 0 &&
    trimmedNew.length <= MAX_LENGTH &&
    !allPlatforms.some((p) => p.name.toLowerCase() === trimmedNew.toLowerCase())

  const handleCreatePlatform = () => {
    if (!canCreate) return
    onChange(trimmedNew)
    setNewPlatformName('')
    setShowCreate(false)
  }

  if (showCreate) {
    return (
      <div className="space-y-2 rounded-lg border p-3">
        <div className="flex items-center justify-between">
          <Label className="text-xs font-medium">Nouvelle plateforme</Label>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-auto py-0 px-1 text-xs"
            onClick={() => { setShowCreate(false); setNewPlatformName('') }}
          >
            <X className="h-3 w-3" />
          </Button>
        </div>
        <div className="flex gap-2">
          <Input
            placeholder="Nom de la plateforme..."
            value={newPlatformName}
            onChange={(e) => setNewPlatformName(e.target.value)}
            maxLength={MAX_LENGTH}
            autoFocus
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleCreatePlatform() } }}
          />
          <Button
            type="button"
            size="sm"
            disabled={!canCreate}
            onClick={handleCreatePlatform}
          >
            <Plus className="h-3 w-3 mr-1" />
            Ajouter
          </Button>
        </div>
        {trimmedNew.length > 0 && !canCreate && trimmedNew.length <= MAX_LENGTH && (
          <p className="text-xs text-muted-foreground">Cette plateforme existe déjà</p>
        )}
        {trimmedNew.length > MAX_LENGTH && (
          <p className="text-xs text-destructive">50 caractères max</p>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              role="combobox"
              aria-expanded={open}
              className="w-full justify-between font-normal"
            >
              <span className={cn(!value && 'text-muted-foreground')}>
                {value || placeholder}
              </span>
              <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
            <Command shouldFilter={true}>
              <CommandInput
                placeholder="Rechercher..."
                value={search}
                onValueChange={setSearch}
              />
              <CommandList>
                <CommandEmpty>Aucune plateforme trouvée</CommandEmpty>

                <CommandGroup heading="Exchanges">
                  {exchanges.map((p) => (
                    <CommandItem key={p.name} value={p.name} onSelect={() => handleSelect(p.name)}>
                      <Check className={cn('mr-2 h-4 w-4', value === p.name ? 'opacity-100' : 'opacity-0')} />
                      {p.name}
                    </CommandItem>
                  ))}
                </CommandGroup>

                <CommandGroup heading="Cold Wallets">
                  {wallets.map((p) => (
                    <CommandItem key={p.name} value={p.name} onSelect={() => handleSelect(p.name)}>
                      <Check className={cn('mr-2 h-4 w-4', value === p.name ? 'opacity-100' : 'opacity-0')} />
                      {p.name}
                    </CommandItem>
                  ))}
                </CommandGroup>

                {custom.length > 0 && (
                  <CommandGroup heading="Mes plateformes">
                    {custom.map((p) => (
                      <CommandItem key={p.name} value={p.name} onSelect={() => handleSelect(p.name)}>
                        <Check className={cn('mr-2 h-4 w-4', value === p.name ? 'opacity-100' : 'opacity-0')} />
                        {p.name}
                      </CommandItem>
                    ))}
                  </CommandGroup>
                )}
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-auto py-1.5 px-2 text-xs text-primary shrink-0"
          onClick={() => setShowCreate(true)}
        >
          <Plus className="h-3 w-3 mr-1" />
          Nouvelle
        </Button>
      </div>
    </div>
  )
}
