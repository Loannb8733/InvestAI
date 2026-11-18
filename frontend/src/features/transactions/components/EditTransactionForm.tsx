import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useToast } from '@/hooks/use-toast'
import { cn, formatCurrency } from '@/lib/utils'
import { changesOf, draftOf, draftTotal, EMPTY_DRAFT, type EditDraft } from '../editDraft'
import { useUpdateTransaction } from '../hooks'
import { ALL_TYPE_BUTTONS, findTypeButton } from '../typeButtons'
import type { Transaction } from '../types'
import PlatformSelect from './PlatformSelect'
import TypeToggle from './TypeToggle'

const COMMON_CURRENCIES = ['EUR', 'USD', 'GBP', 'CHF', 'BTC', 'ETH', 'USDT', 'USDC']
const FIELD_LABEL = 'text-xs text-muted-foreground uppercase tracking-wider'

interface EditTransactionFormProps {
  transaction: Transaction | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className={FIELD_LABEL}>{label}</Label>
      {children}
    </div>
  )
}

function CurrencySelect({ value, onChange, options, placeholder, className }: { value: string; onChange: (v: string) => void; options: string[]; placeholder: string; className?: string }) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className={className}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {options.map((curr) => (
          <SelectItem key={curr} value={curr}>
            {curr}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

export default function EditTransactionForm({ transaction, open, onOpenChange }: EditTransactionFormProps) {
  const { toast } = useToast()
  const [draft, setDraft] = useState<EditDraft>(EMPTY_DRAFT)
  const update = useUpdateTransaction(transaction?.id, () => onOpenChange(false))

  useEffect(() => {
    if (transaction) setDraft((previous) => draftOf(transaction, previous))
  }, [transaction])

  if (!transaction) return null

  const set = (field: keyof EditDraft) => (value: string) => setDraft((d) => ({ ...d, [field]: value }))
  const typeConfig = findTypeButton(ALL_TYPE_BUTTONS, draft.transactionType)
  const total = draftTotal(draft)
  const feeCurrencies = [transaction.asset_symbol, 'EUR', 'USD', 'BTC', 'ETH', 'USDT', 'USDC'].filter((v, i, a) => v && a.indexOf(v) === i)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const updates = changesOf(transaction, draft)
    if (Object.keys(updates).length === 0) {
      toast({ title: 'Aucune modification' })
      onOpenChange(false)
      return
    }
    update.mutate(updates)
  }

  const platformLabel =
    draft.transactionType === 'transfer_in'
      ? 'Sur (plateforme de réception)'
      : draft.transactionType === 'transfer_out'
        ? 'Depuis (plateforme source)'
        : 'Plateforme'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="border-border bg-background/80 shadow-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {typeConfig && <typeConfig.icon className={cn('h-5 w-5', typeConfig.color)} />}
            Modifier — {transaction.asset_symbol}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={submit}>
          <div className="space-y-4 py-3">
            <TypeToggle buttons={ALL_TYPE_BUTTONS} value={draft.transactionType} onChange={set('transactionType')} />
            <div className="grid grid-cols-2 gap-3">
              <Field label="Date">
                <Input type="date" value={draft.executedDate} onChange={(e) => set('executedDate')(e.target.value)} />
              </Field>
              <Field label="Heure">
                <Input type="time" value={draft.executedTime} onChange={(e) => set('executedTime')(e.target.value)} />
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Quantité">
                <Input type="text" inputMode="decimal" value={draft.quantity} onChange={(e) => set('quantity')(e.target.value)} />
              </Field>
              <Field label="Prix unitaire">
                <Input type="text" inputMode="decimal" value={draft.price} onChange={(e) => set('price')(e.target.value)} />
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Frais">
                <div className="flex gap-2">
                  <Input type="text" inputMode="decimal" value={draft.fee} onChange={(e) => set('fee')(e.target.value)} placeholder="0" className="flex-1" />
                  <CurrencySelect value={draft.feeCurrency} onChange={set('feeCurrency')} options={feeCurrencies} placeholder="..." className="w-24" />
                </div>
              </Field>
              <Field label="Devise">
                <CurrencySelect value={draft.currency} onChange={set('currency')} options={COMMON_CURRENCIES} placeholder="Devise..." />
              </Field>
            </div>
            <Field label={platformLabel}>
              <PlatformSelect value={draft.exchange} onChange={set('exchange')} showTrustBadge />
            </Field>
            <Field label="Notes">
              <Textarea value={draft.notes} onChange={(e) => set('notes')(e.target.value)} placeholder="Notes optionnelles..." rows={2} />
            </Field>
            {total > 0 && (
              <div className="rounded-xl border border-border bg-muted/30 px-3 py-2">
                <div className="flex justify-between items-center">
                  <span className="text-xs text-muted-foreground">Montant total</span>
                  <span className="text-sm font-semibold">{formatCurrency(total)}</span>
                </div>
              </div>
            )}
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Annuler
            </Button>
            <Button type="submit" disabled={update.isPending} className={cn('text-white transition-colors', typeConfig?.submitBg)}>
              {update.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Enregistrer
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
