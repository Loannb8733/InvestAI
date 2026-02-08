import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useToast } from '@/hooks/use-toast'
import { portfoliosApi } from '@/services/api'
import { Loader2, Trash2 } from 'lucide-react'

const COMMON_EXCHANGES = [
  'Crypto.com',
  'Binance',
  'Kraken',
  'Coinbase',
  'Bitstamp',
  'KuCoin',
  'Bybit',
  'OKX',
  'Gate.io',
  'Revolut',
  'Trade Republic',
  'Autre',
]

interface CashBalanceFormProps {
  portfolioId: string
  cashBalances: Record<string, number>
  open: boolean
  onOpenChange: (open: boolean) => void
}

export default function CashBalanceForm({
  portfolioId,
  cashBalances,
  open,
  onOpenChange,
}: CashBalanceFormProps) {
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const [exchange, setExchange] = useState('')
  const [customExchange, setCustomExchange] = useState('')
  const [amount, setAmount] = useState('')

  const updateMutation = useMutation({
    mutationFn: ({ exchange, amount }: { exchange: string; amount: number }) =>
      portfoliosApi.updateCashBalance(portfolioId, exchange, amount),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['portfolios'] })
      toast({ title: 'Solde mis à jour' })
      setExchange('')
      setCustomExchange('')
      setAmount('')
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de mettre à jour le solde' })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (exchange: string) =>
      portfoliosApi.deleteCashBalance(portfolioId, exchange),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['portfolios'] })
      toast({ title: 'Solde supprimé' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de supprimer le solde' })
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
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

    updateMutation.mutate({ exchange: selectedExchange, amount: amountValue })
  }

  const totalCash = Object.values(cashBalances || {}).reduce((sum, val) => sum + val, 0)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Gérer le cash disponible</DialogTitle>
          <DialogDescription>
            Ajoutez ou modifiez vos soldes EUR sur vos plateformes d'échange.
          </DialogDescription>
        </DialogHeader>

        {/* Current balances */}
        {Object.keys(cashBalances || {}).length > 0 && (
          <div className="space-y-2">
            <Label>Soldes actuels</Label>
            <div className="space-y-2 max-h-40 overflow-y-auto">
              {Object.entries(cashBalances || {}).map(([ex, amt]) => (
                <div key={ex} className="flex items-center justify-between p-2 rounded bg-muted">
                  <span className="font-medium">{ex}</span>
                  <div className="flex items-center gap-2">
                    <span>{amt.toFixed(2)} €</span>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6"
                      onClick={() => deleteMutation.mutate(ex)}
                      disabled={deleteMutation.isPending}
                    >
                      <Trash2 className="h-3 w-3 text-destructive" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
            <div className="text-right text-sm text-muted-foreground">
              Total: <span className="font-bold text-foreground">{totalCash.toFixed(2)} €</span>
            </div>
          </div>
        )}

        {/* Add/Update form */}
        <form onSubmit={handleSubmit} className="space-y-4 pt-2 border-t">
          <div className="space-y-2">
            <Label>Plateforme</Label>
            <Select value={exchange} onValueChange={setExchange}>
              <SelectTrigger>
                <SelectValue placeholder="Sélectionner une plateforme" />
              </SelectTrigger>
              <SelectContent>
                {COMMON_EXCHANGES.map((ex) => (
                  <SelectItem key={ex} value={ex}>
                    {ex}
                  </SelectItem>
                ))}
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
            <Input
              id="amount"
              type="number"
              step="0.01"
              min="0"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0.00"
            />
          </div>

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Fermer
            </Button>
            <Button type="submit" disabled={updateMutation.isPending}>
              {updateMutation.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Ajouter / Modifier
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
