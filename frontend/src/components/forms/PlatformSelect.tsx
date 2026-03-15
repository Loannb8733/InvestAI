import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Check, ChevronsUpDown, Plus } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
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

  const { data } = useQuery({
    queryKey: ['user-platforms'],
    queryFn: () => transactionsApi.getPlatforms(),
    staleTime: 60_000,
  })

  const userPlatforms = data?.platforms ?? []

  // Merge known platforms + user platforms, deduplicated case-insensitively
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

  const trimmedSearch = search.trim()
  const canCreate =
    trimmedSearch.length > 0 &&
    trimmedSearch.length <= MAX_LENGTH &&
    !allPlatforms.some((p) => p.name.toLowerCase() === trimmedSearch.toLowerCase())

  const handleSelect = (name: string) => {
    onChange(name)
    setOpen(false)
    setSearch('')
  }

  const handleCreate = () => {
    if (!canCreate) return
    onChange(trimmedSearch)
    setOpen(false)
    setSearch('')
  }

  return (
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
            placeholder="Rechercher une plateforme..."
            value={search}
            onValueChange={setSearch}
          />
          <CommandList>
            <CommandEmpty>
              {trimmedSearch.length > MAX_LENGTH ? (
                <span className="text-destructive text-xs">50 caractères max</span>
              ) : (
                'Aucune plateforme trouvée'
              )}
            </CommandEmpty>

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

            {canCreate && (
              <CommandGroup>
                <CommandItem onSelect={handleCreate} className="text-primary">
                  <Plus className="mr-2 h-4 w-4" />
                  Ajouter &laquo;{trimmedSearch}&raquo;
                </CommandItem>
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
