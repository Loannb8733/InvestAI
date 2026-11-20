import { useState, type FormEvent } from 'react'
import { Loader2, Trash2, Wallet } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useColdWallets, useDeleteColdWallet, useSaveColdWallet } from '../coldWallets'
import type { ColdWallet } from '../types'

function WalletList({ wallets, deleting, onDelete }: { wallets: ColdWallet[]; deleting: boolean; onDelete: (id: string) => void }) {
  return (
    <ul className="divide-y divide-border/60 rounded-lg border border-border/60">
      {wallets.map((wallet) => (
        <li key={wallet.id} className="flex items-center justify-between gap-3 px-4 py-3">
          <div className="min-w-0">
            <p className="font-medium">{wallet.label}</p>
            <p className="truncate font-mono text-xs text-muted-foreground" title={wallet.address}>
              {wallet.address}
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Supprimer ${wallet.label}`}
            disabled={deleting}
            onClick={() => onDelete(wallet.id)}
          >
            <Trash2 className="h-4 w-4" aria-hidden />
          </Button>
        </li>
      ))}
    </ul>
  )
}

export default function ColdWalletsManager() {
  const [address, setAddress] = useState('')
  const [label, setLabel] = useState('')
  const { data: wallets, isLoading, isError, isFetching, refetch } = useColdWallets()
  const save = useSaveColdWallet(() => {
    setAddress('')
    setLabel('')
  })
  const remove = useDeleteColdWallet()

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    const trimmedAddress = address.trim()
    const trimmedLabel = label.trim()
    if (!trimmedAddress || !trimmedLabel) return
    save.mutate({ address: trimmedAddress, label: trimmedLabel })
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
              onChange={(event) => setAddress(event.target.value)}
              placeholder="bc1q… / 0x…"
              autoComplete="off"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="cw-label">Nom du wallet</Label>
            <Input
              id="cw-label"
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              placeholder="Ledger"
              maxLength={50}
            />
          </div>
          <Button type="submit" disabled={save.isPending || !address.trim() || !label.trim()}>
            {save.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden />}
            Ajouter
          </Button>
        </form>

        {isLoading ? (
          <p className="text-sm text-muted-foreground">Chargement…</p>
        ) : isError ? (
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-sm text-destructive">Impossible de charger les cold wallets.</p>
            <Button variant="outline" size="sm" disabled={isFetching} onClick={() => refetch()}>
              {isFetching && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden />}
              Réessayer
            </Button>
          </div>
        ) : !wallets || wallets.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Aucun cold wallet nommé. Ajoutez une adresse pour la router automatiquement.
          </p>
        ) : (
          <WalletList wallets={wallets} deleting={remove.isPending} onDelete={(id) => remove.mutate(id)} />
        )}
      </CardContent>
    </Card>
  )
}
