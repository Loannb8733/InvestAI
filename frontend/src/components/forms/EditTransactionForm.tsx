import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog,
  DialogContent,
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
import {
  ArrowDownRight,
  ArrowLeftRight,
  ArrowUpRight,
  Gift,
  Loader2,
  Coins,
  Lock,
  Unlock,
  TrendingUp,
  Percent,
} from 'lucide-react'
import { invalidateAllFinancialData } from '@/lib/invalidate-queries'
import { PlatformSelect } from '@/components/forms/PlatformSelect'
import { cn } from '@/lib/utils'
import type { TransactionEdit as Transaction } from '@/types'

interface EditTransactionFormProps {
  transaction: Transaction | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess?: () => void
}

const TRANSACTION_TYPES = [
  { value: 'buy', label: 'Achat', shortLabel: 'Achat', icon: ArrowDownRight, color: 'text-gain', bg: 'bg-gain/10 border-gain/20', activeBg: 'bg-gain/20 border-gain/40 ring-1 ring-gain/30', submitBg: 'bg-gain hover:bg-gain' },
  { value: 'sell', label: 'Vente', shortLabel: 'Vente', icon: ArrowUpRight, color: 'text-loss', bg: 'bg-loss/10 border-loss/20', activeBg: 'bg-loss/20 border-loss/40 ring-1 ring-loss/30', submitBg: 'bg-loss hover:bg-loss' },
  { value: 'transfer_in', label: 'Transfert entrant', shortLabel: 'Transfert In', icon: ArrowDownRight, color: 'text-accent', bg: 'bg-accent/10 border-accent/20', activeBg: 'bg-accent/20 border-accent/40 ring-1 ring-accent/30', submitBg: 'bg-accent hover:bg-accent' },
  { value: 'transfer_out', label: 'Transfert sortant', shortLabel: 'Transfert Out', icon: ArrowUpRight, color: 'text-warning', bg: 'bg-warning/10 border-warning/20', activeBg: 'bg-warning/20 border-warning/40 ring-1 ring-warning/30', submitBg: 'bg-warning hover:bg-warning' },
  { value: 'staking_reward', label: 'Reward', shortLabel: 'Reward', icon: Coins, color: 'text-warning', bg: 'bg-warning/10 border-warning/20', activeBg: 'bg-warning/20 border-warning/40 ring-1 ring-warning/30', submitBg: 'bg-warning hover:bg-warning' },
  { value: 'airdrop', label: 'Airdrop', shortLabel: 'Airdrop', icon: Gift, color: 'text-accent', bg: 'bg-accent/10 border-accent/20', activeBg: 'bg-accent/20 border-accent/40 ring-1 ring-accent/30', submitBg: 'bg-accent hover:bg-accent' },
  { value: 'conversion_in', label: 'Conversion entrante', shortLabel: 'Conv. In', icon: ArrowLeftRight, color: 'text-gain', bg: 'bg-gain/10 border-gain/20', activeBg: 'bg-gain/20 border-gain/40 ring-1 ring-gain/30', submitBg: 'bg-gain hover:bg-gain' },
  { value: 'conversion_out', label: 'Conversion sortante', shortLabel: 'Conv. Out', icon: ArrowLeftRight, color: 'text-warning', bg: 'bg-warning/10 border-warning/20', activeBg: 'bg-warning/20 border-warning/40 ring-1 ring-warning/30', submitBg: 'bg-warning hover:bg-warning' },
  { value: 'staking', label: 'Staking', shortLabel: 'Staking', icon: Lock, color: 'text-accent', bg: 'bg-accent/10 border-accent/20', activeBg: 'bg-accent/20 border-accent/40 ring-1 ring-accent/30', submitBg: 'bg-accent hover:bg-accent' },
  { value: 'unstaking', label: 'Unstaking', shortLabel: 'Unstaking', icon: Unlock, color: 'text-accent', bg: 'bg-accent/10 border-accent/20', activeBg: 'bg-accent/20 border-accent/40 ring-1 ring-accent/30', submitBg: 'bg-accent hover:bg-accent' },
  { value: 'dividend', label: 'Dividende', shortLabel: 'Dividende', icon: TrendingUp, color: 'text-gain', bg: 'bg-gain/10 border-gain/20', activeBg: 'bg-gain/20 border-gain/40 ring-1 ring-gain/30', submitBg: 'bg-gain hover:bg-gain' },
  { value: 'interest', label: 'Intérêt', shortLabel: 'Intérêt', icon: Percent, color: 'text-accent', bg: 'bg-accent/10 border-accent/20', activeBg: 'bg-accent/20 border-accent/40 ring-1 ring-accent/30', submitBg: 'bg-accent hover:bg-accent' },
] as const

const COMMON_CURRENCIES = ['EUR', 'USD', 'GBP', 'CHF', 'BTC', 'ETH', 'USDT', 'USDC']

const fmt = new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' })

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

  const typeConfig = TRANSACTION_TYPES.find((t) => t.value === transactionType)

  const toNum = (v: string) => { const n = parseFloat(v); return isNaN(n) ? 0 : n }
  const total = toNum(quantity) * toNum(price) + toNum(fee)

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
      <DialogContent className="border-border bg-background/80 shadow-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {typeConfig && <typeConfig.icon className={cn('h-5 w-5', typeConfig.color)} />}
            Modifier — {transaction.asset_symbol}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit}>
          <div className="space-y-4 py-3">
            {/* Transaction Type — Toggle Group */}
            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground uppercase tracking-wider">Type de transaction</Label>
              <div className="grid grid-cols-4 gap-1.5">
                {TRANSACTION_TYPES.map((type) => {
                  const Icon = type.icon
                  const isActive = transactionType === type.value
                  return (
                    <button
                      key={type.value}
                      type="button"
                      aria-label={type.label}
                      aria-pressed={isActive}
                      onClick={() => setTransactionType(type.value)}
                      className={cn(
                        'flex flex-col items-center gap-1 rounded-lg border px-2 py-2 text-[11px] font-medium transition-all duration-150',
                        isActive ? type.activeBg : `${type.bg} hover:opacity-80 opacity-60`,
                      )}
                    >
                      <Icon className={cn('h-4 w-4', type.color)} />
                      <span className={cn('truncate w-full text-center', isActive ? 'text-foreground' : 'text-muted-foreground')}>
                        {type.shortLabel}
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Date + Time */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground uppercase tracking-wider">Date</Label>
                <Input
                  type="date"
                  value={executedDate}
                  onChange={(e) => setExecutedDate(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground uppercase tracking-wider">Heure</Label>
                <Input
                  type="time"
                  value={executedTime}
                  onChange={(e) => setExecutedTime(e.target.value)}
                />
              </div>
            </div>

            {/* Quantity + Price */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground uppercase tracking-wider">Quantité</Label>
                <Input
                  type="text"
                  inputMode="decimal"
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground uppercase tracking-wider">Prix unitaire</Label>
                <Input
                  type="text"
                  inputMode="decimal"
                  value={price}
                  onChange={(e) => setPrice(e.target.value)}
                />
              </div>
            </div>

            {/* Fee + Currency */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground uppercase tracking-wider">Frais</Label>
                <div className="flex gap-2">
                  <Input
                    type="text"
                    inputMode="decimal"
                    value={fee}
                    onChange={(e) => setFee(e.target.value)}
                    placeholder="0"
                    className="flex-1"
                  />
                  <Select value={feeCurrency} onValueChange={setFeeCurrency}>
                    <SelectTrigger className="w-24">
                      <SelectValue placeholder="..." />
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
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground uppercase tracking-wider">Devise</Label>
                <Select value={currency} onValueChange={setCurrency}>
                  <SelectTrigger>
                    <SelectValue placeholder="Devise..." />
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
            </div>

            {/* Platform */}
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground uppercase tracking-wider">
                {transactionType === 'transfer_in'
                  ? 'Sur (plateforme de réception)'
                  : transactionType === 'transfer_out'
                    ? 'Depuis (plateforme source)'
                    : 'Plateforme'}
              </Label>
              <PlatformSelect
                value={exchange}
                onChange={setExchange}
                showTrustBadge
              />
            </div>

            {/* Notes */}
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground uppercase tracking-wider">Notes</Label>
              <Textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Notes optionnelles..."
                rows={2}
              />
            </div>

            {/* Total preview */}
            {total > 0 && (
              <div className="rounded-xl border border-border bg-muted/30 px-3 py-2">
                <div className="flex justify-between items-center">
                  <span className="text-xs text-muted-foreground">Montant total</span>
                  <span className="text-sm font-semibold">{fmt.format(total)}</span>
                </div>
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Annuler
            </Button>
            <Button
              type="submit"
              disabled={updateMutation.isPending}
              className={cn('text-white transition-colors', typeConfig?.submitBg)}
            >
              {updateMutation.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Enregistrer
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
