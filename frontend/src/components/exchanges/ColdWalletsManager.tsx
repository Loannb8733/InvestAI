import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Trash2, Wallet } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useToast } from '@/hooks/use-toast'
import { coldWalletsApi, type ColdWallet } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'

/**
 * Manage the address → name mapping used by the scheduled sync to route each
 * exchange withdrawal to the right named cold wallet (Tangem, Ledger, …).
 * Unmapped addresses fall back to the default ("Tangem").
 */
export default function ColdWalletsManager() {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [address, setAddress] = useState('')
  const [label, setLabel] = useState('')

  const {
    data: wallets,
    isLoading,
    isError,
  } = useQuery<ColdWallet[]>({
    queryKey: queryKeys.coldWallets.list,
    queryFn: coldWalletsApi.list,
  })

  const upsertMutation = useMutation({
    mutationFn: coldWalletsApi.upsert,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.coldWallets.all })
      setAddress('')
      setLabel('')
      toast({ title: 'Cold wallet enregistré', description: 'L’adresse a été associée à ce nom.' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible d’enregistrer ce cold wallet.' })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: coldWalletsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.coldWallets.all })
      toast({ title: 'Cold wallet supprimé' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de supprimer ce cold wallet.' })
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const addr = address.trim()
    const name = label.trim()
    if (!addr || !name) return
    upsertMutation.mutate({ address: addr, label: name })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-serif">
          <Wallet className="h-5 w-5" aria-hidden />
          Cold wallets
        </CardTitle>
        <CardDescription>
          Associez vos adresses de retrait à un nom (Tangem, Ledger…). La synchronisation routera chaque
          retrait vers le bon cold wallet ; une adresse inconnue retombe sur « Tangem » par défaut.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <form onSubmit={handleSubmit} className="grid gap-3 sm:grid-cols-[1fr_180px_auto] sm:items-end">
          <div className="space-y-2">
            <Label htmlFor="cw-address">Adresse de retrait</Label>
            <Input
              id="cw-address"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="bc1q… / 0x…"
              autoComplete="off"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="cw-label">Nom du wallet</Label>
            <Input
              id="cw-label"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Ledger"
              maxLength={50}
            />
          </div>
          <Button type="submit" disabled={upsertMutation.isPending || !address.trim() || !label.trim()}>
            {upsertMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden />}
            Ajouter
          </Button>
        </form>

        {isLoading ? (
          <p className="text-sm text-muted-foreground">Chargement…</p>
        ) : isError ? (
          <p className="text-sm text-destructive">Impossible de charger les cold wallets. Réessayez.</p>
        ) : !wallets || wallets.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Aucun cold wallet nommé. Ajoutez une adresse pour la router automatiquement.
          </p>
        ) : (
          <ul className="divide-y divide-border/60 rounded-lg border border-border/60">
            {wallets.map((w) => (
              <li key={w.id} className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <p className="font-medium">{w.label}</p>
                  <p className="truncate font-mono text-xs text-muted-foreground" title={w.address}>
                    {w.address}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Supprimer ${w.label}`}
                  disabled={deleteMutation.isPending}
                  onClick={() => deleteMutation.mutate(w.id)}
                >
                  <Trash2 className="h-4 w-4" aria-hidden />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
