import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'
import { transactionsApi } from '@/services/api'
import { Loader2 } from 'lucide-react'
import { invalidateAllFinancialData } from '@/lib/invalidate-queries'

interface Transaction {
  id: string
  asset_symbol: string
  transaction_type: string
  quantity: number
  price: number
  fee: number | null
  fee_currency?: string | null
  currency: string
  executed_at: string
  exchange?: string | null
  notes: string | null
}

interface EditTransactionFormProps {
  transaction: Transaction | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess?: () => void
}

const TRANSACTION_TYPES = [
  { value: 'buy', label: 'Achat' },
  { value: 'sell', label: 'Vente' },
  { value: 'transfer_in', label: 'Transfert entrant' },
  { value: 'transfer_out', label: 'Transfert sortant' },
  { value: 'staking_reward', label: 'Récompense staking' },
  { value: 'airdrop', label: 'Airdrop' },
  { value: 'conversion_in', label: 'Conversion entrante' },
  { value: 'conversion_out', label: 'Conversion sortante' },
]

const COMMON_CURRENCIES = ['EUR', 'USD', 'GBP', 'CHF', 'BTC', 'ETH', 'USDT', 'USDC']

export default function EditTransactionForm({
  transaction,
  open,
  onOpenChange,
  onSuccess,
}: EditTransactionFormProps) {
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const [transactionType, setTransactionType] = useState('')
  const [quantity, setQuantity] = useState('')
  const [price, setPrice] = useState('')
  const [fee, setFee] = useState('')
  const [feeCurrency, setFeeCurrency] = useState('')
  const [currency, setCurrency] = useState('')
  const [executedDate, setExecutedDate] = useState('')
  const [executedTime, setExecutedTime] = useState('')
  const [exchange, setExchange] = useState('')
  const [notes, setNotes] = useState('')

  // Reset form when transaction changes
  useEffect(() => {
    if (transaction) {
      setTransactionType(transaction.transaction_type)
      setQuantity(transaction.quantity.toString())
      setPrice(transaction.price.toString())
      setFee((transaction.fee ?? 0).toString())
      setFeeCurrency(transaction.fee_currency || transaction.asset_symbol || '')
      setCurrency(transaction.currency || 'EUR')
      setExchange(transaction.exchange || '')
      setNotes(transaction.notes || '')

      // Parse datetime
      if (transaction.executed_at) {
        const date = new Date(transaction.executed_at)
        setExecutedDate(date.toISOString().split('T')[0])
        setExecutedTime(date.toTimeString().slice(0, 5))
      }
    }
  }, [transaction])

  const updateMutation = useMutation({
    mutationFn: (data: {
      transaction_type?: string
      quantity?: number
      price?: number
      fee?: number
      fee_currency?: string
      currency?: string
      executed_at?: string
      exchange?: string
      notes?: string
    }) => transactionsApi.update(transaction!.id, data),
    onSuccess: () => {
      invalidateAllFinancialData(queryClient)
      toast({ title: 'Transaction mise à jour' })
      onOpenChange(false)
      onSuccess?.()
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de mettre à jour la transaction' })
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!transaction) return

    const updates: {
      transaction_type?: string
      quantity?: number
      price?: number
      fee?: number
      fee_currency?: string
      currency?: string
      executed_at?: string
      exchange?: string
      notes?: string
    } = {}

    const newQuantity = parseFloat(quantity)
    const newPrice = parseFloat(price)
    const newFee = parseFloat(fee)

    if (transactionType && transactionType !== transaction.transaction_type) {
      updates.transaction_type = transactionType
    }
    if (!isNaN(newQuantity) && newQuantity !== transaction.quantity) {
      updates.quantity = newQuantity
    }
    if (!isNaN(newPrice) && newPrice !== transaction.price) {
      updates.price = newPrice
    }
    if (!isNaN(newFee) && newFee !== (transaction.fee ?? 0)) {
      updates.fee = newFee
    }
    if (feeCurrency && feeCurrency !== (transaction.fee_currency || '')) {
      updates.fee_currency = feeCurrency
    }
    if (currency && currency !== transaction.currency) {
      updates.currency = currency
    }
    if (executedDate && executedTime) {
      const newExecutedAt = `${executedDate}T${executedTime}:00`
      const oldDate = new Date(transaction.executed_at)
      const newDate = new Date(newExecutedAt)
      if (oldDate.getTime() !== newDate.getTime()) {
        updates.executed_at = newExecutedAt
      }
    }
    if (exchange !== (transaction.exchange || '')) {
      updates.exchange = exchange || undefined
    }
    if (notes !== (transaction.notes || '')) {
      updates.notes = notes
    }

    if (Object.keys(updates).length === 0) {
      toast({ title: 'Aucune modification' })
      onOpenChange(false)
      return
    }

    updateMutation.mutate(updates)
  }

  if (!transaction) return null

  // Common fee currencies
  const suggestedFeeCurrencies = [
    transaction.asset_symbol,
    'EUR',
    'USD',
    'BTC',
    'ETH',
    'USDT',
    'USDC',
  ].filter((v, i, a) => v && a.indexOf(v) === i)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Modifier la transaction</DialogTitle>
          <DialogDescription>
            {transaction.asset_symbol}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Transaction Type */}
          <div className="space-y-2">
            <Label htmlFor="transactionType">Type de transaction</Label>
            <Select value={transactionType} onValueChange={setTransactionType}>
              <SelectTrigger>
                <SelectValue placeholder="Sélectionner un type" />
              </SelectTrigger>
              <SelectContent>
                {TRANSACTION_TYPES.map((type) => (
                  <SelectItem key={type.value} value={type.value}>
                    {type.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Date and Time */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="executedDate">Date</Label>
              <Input
                id="executedDate"
                type="date"
                value={executedDate}
                onChange={(e) => setExecutedDate(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="executedTime">Heure</Label>
              <Input
                id="executedTime"
                type="time"
                value={executedTime}
                onChange={(e) => setExecutedTime(e.target.value)}
              />
            </div>
          </div>

          {/* Quantity and Price */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="quantity">Quantité</Label>
              <Input
                id="quantity"
                type="number"
                step="any"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="price">Prix unitaire</Label>
              <Input
                id="price"
                type="number"
                step="any"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
              />
            </div>
          </div>

          {/* Currency */}
          <div className="space-y-2">
            <Label htmlFor="currency">Devise de la transaction</Label>
            <Select value={currency} onValueChange={setCurrency}>
              <SelectTrigger>
                <SelectValue placeholder="Sélectionner une devise" />
              </SelectTrigger>
              <SelectContent>
                {COMMON_CURRENCIES.map((curr) => (
                  <SelectItem key={curr} value={curr}>
                    {curr}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Fee */}
          <div className="space-y-2">
            <Label>Frais de transaction</Label>
            <div className="flex gap-2">
              <Input
                id="fee"
                type="number"
                step="any"
                value={fee}
                onChange={(e) => setFee(e.target.value)}
                placeholder="0"
                className="flex-1"
              />
              <Select value={feeCurrency} onValueChange={setFeeCurrency}>
                <SelectTrigger className="w-32">
                  <SelectValue placeholder="Devise" />
                </SelectTrigger>
                <SelectContent>
                  {suggestedFeeCurrencies.map((curr) => (
                    <SelectItem key={curr} value={curr}>
                      {curr}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <p className="text-xs text-muted-foreground">
              Les frais peuvent être dans l'actif échangé ou en fiat
            </p>
          </div>

          {/* Exchange */}
          <div className="space-y-2">
            <Label htmlFor="exchange">Plateforme / Exchange</Label>
            <Input
              id="exchange"
              type="text"
              value={exchange}
              onChange={(e) => setExchange(e.target.value)}
              placeholder="Ex: Binance, Kraken, Crypto.com..."
            />
          </div>

          {/* Notes */}
          <div className="space-y-2">
            <Label htmlFor="notes">Notes</Label>
            <Textarea
              id="notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Notes optionnelles..."
              rows={2}
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Annuler
            </Button>
            <Button type="submit" disabled={updateMutation.isPending}>
              {updateMutation.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Enregistrer
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
