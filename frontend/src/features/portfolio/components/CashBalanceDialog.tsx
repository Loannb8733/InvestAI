import { useState, type FormEvent } from 'react'
import { Loader2, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useToast } from '@/hooks/use-toast'
import { COLD_WALLETS, EXCHANGES } from '@/lib/platforms'
import { formatCurrency } from '@/lib/utils'
import { useCashBalance } from '../hooks'

interface CashBalanceDialogProps {
  portfolioId: string
  cashBalances: Record<string, number>
  open: boolean
  onOpenChange: (open: boolean) => void
}

function CurrentBalances({ cashBalances, onDelete, deleting }: { cashBalances: Record<string, number>; onDelete: (exchange: string) => void; deleting: boolean }) {
  const totalCash = Object.values(cashBalances).reduce((sum, val) => sum + val, 0)
  return (
    <div className="space-y-2">
      <Label>Soldes actuels</Label>
      <div className="space-y-2 max-h-40 overflow-y-auto">
        {Object.entries(cashBalances).map(([ex, amt]) => (
          <div key={ex} className="flex items-center justify-between p-2 rounded bg-muted">
            <span className="font-medium">{ex}</span>
            <div className="flex items-center gap-2">
              <span>{formatCurrency(amt)}</span>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 tap-target"
                onClick={() => onDelete(ex)}
                aria-label="Supprimer ce solde"
                disabled={deleting}
              >
                <Trash2 className="h-3 w-3 text-destructive" />
              </Button>
            </div>
          </div>
        ))}
      </div>
      <div className="text-right text-sm text-muted-foreground">
        Total: <span className="font-bold text-foreground">{formatCurrency(totalCash)}</span>
      </div>
    </div>
  )
}

export default function CashBalanceDialog({ portfolioId, cashBalances, open, onOpenChange }: CashBalanceDialogProps) {
  const { toast } = useToast()
  const [exchange, setExchange] = useState('')
  const [customExchange, setCustomExchange] = useState('')
  const [amount, setAmount] = useState('')
  const { save, remove } = useCashBalance(portfolioId, () => {
    setExchange('')
    setCustomExchange('')
    setAmount('')
  })

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    const selectedExchange = exchange === 'Autre' ? customExchange : exchange
    const amountValue = parseFloat(amount)
    if (!selectedExchange) {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Sélectionnez une plateforme' })
      return
    }
    if (isNaN(amountValue) || amountValue < 0) {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Montant invalide' })
      return
    }
    save.mutate({ exchange: selectedExchange, amount: amountValue })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Gérer le cash disponible</DialogTitle>
          <DialogDescription>Ajoutez ou modifiez vos soldes EUR sur vos plateformes d'échange.</DialogDescription>
        </DialogHeader>

        {Object.keys(cashBalances).length > 0 && (
          <CurrentBalances cashBalances={cashBalances} onDelete={(ex) => remove.mutate(ex)} deleting={remove.isPending} />
        )}

        <form onSubmit={handleSubmit} className="space-y-4 pt-2 border-t">
          <div className="space-y-2">
            <Label>Plateforme</Label>
            <Select value={exchange} onValueChange={setExchange}>
              <SelectTrigger>
                <SelectValue placeholder="Sélectionner une plateforme" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectLabel>Exchanges</SelectLabel>
                  {EXCHANGES.map((ex) => (
                    <SelectItem key={ex} value={ex}>{ex}</SelectItem>
                  ))}
                </SelectGroup>
                <SelectGroup>
                  <SelectLabel>Cold Wallets</SelectLabel>
                  {COLD_WALLETS.map((ex) => (
                    <SelectItem key={ex} value={ex}>{ex}</SelectItem>
                  ))}
                </SelectGroup>
                <SelectItem value="Autre">Autre</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {exchange === 'Autre' && (
            <div className="space-y-2">
              <Label htmlFor="customExchange">Nom de la plateforme</Label>
              <Input
                id="customExchange"
                value={customExchange}
                onChange={(e) => setCustomExchange(e.target.value)}
                placeholder="Ex: Boursorama, Degiro..."
              />
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="amount">Montant (EUR)</Label>
            <Input id="amount" type="number" step="0.01" min="0" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" />
          </div>

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Fermer
            </Button>
            <Button type="submit" disabled={save.isPending}>
              {save.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Ajouter / Modifier
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
