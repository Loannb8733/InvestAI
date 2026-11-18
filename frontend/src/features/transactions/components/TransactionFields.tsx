import type { ReactNode } from 'react'
import type { UseFormReturn } from 'react-hook-form'
import { TrendingUp } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { AddInput, AddOutput } from '../addSchema'
import type { TotalInput } from '../useTotalInput'
import PlatformSelect from './PlatformSelect'

interface TransactionFieldsProps {
  form: UseFormReturn<AddInput, unknown, AddOutput>
  type: string
  currency: string
  amounts: TotalInput
  marketPrice: number | undefined
  format: (value: number) => string
  destination: string
  onDestinationChange: (value: string) => void
}

const LABEL = 'text-xs text-muted-foreground uppercase tracking-wider'

function Field({ id, label, extra, error, children }: { id?: string; label: ReactNode; extra?: ReactNode; error?: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      {extra !== undefined ? (
        <div className="flex items-center justify-between">
          <Label htmlFor={id} className={LABEL}>{label}</Label>
          {extra}
        </div>
      ) : (
        <Label htmlFor={id} className={LABEL}>{label}</Label>
      )}
      {children}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}

const PLATFORM_LABELS: Record<string, string> = {
  transfer_in: 'Sur (plateforme de réception)',
  transfer_out: 'Depuis (plateforme source)',
}

export default function TransactionFields(props: TransactionFieldsProps) {
  const { form, type, currency, amounts, marketPrice, format, destination, onDestinationChange } = props
  const { register, watch, setValue, formState } = form
  const price = register('price')
  const fee = register('fee')
  const decimal = { type: 'text', inputMode: 'decimal', placeholder: '0.00' } as const

  return (
    <>
      <div className="space-y-2">
        <Label className={LABEL}>{PLATFORM_LABELS[type] ?? 'Plateforme'}</Label>
        <PlatformSelect value={watch('exchange') || ''} onChange={(value) => setValue('exchange', value)} showTrustBadge />
        {type === 'transfer_in' && <p className="text-[10px] text-muted-foreground">Plateforme où l'actif est reçu (ex: Tangem, Ledger...)</p>}
      </div>
      {type === 'transfer_out' && (
        <div className="space-y-2">
          <Label className={LABEL}>Vers (plateforme destination)</Label>
          <PlatformSelect value={destination} onChange={onDestinationChange} placeholder="Cold wallet, autre exchange..." showTrustBadge />
          <p className="text-[10px] text-muted-foreground">
            Un transfert entrant sera créé automatiquement sur la destination ; sans destination, sur le wallet froid par défaut
            (Tangem)
          </p>
        </div>
      )}
      <div className="grid grid-cols-2 gap-3">
        <Field id="quantity" label="Quantité" error={formState.errors.quantity?.message}>
          <Input id="quantity" {...decimal} {...register('quantity')} onBlur={amounts.stop} />
        </Field>
        <Field
          id="price"
          label="Prix unitaire"
          error={formState.errors.price?.message}
          extra={
            marketPrice != null &&
            marketPrice > 0 && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-auto py-0 px-1 text-[10px] text-primary gap-1"
                onClick={() => amounts.applyPrice(marketPrice)}
                title={`Prix actuel: ${format(marketPrice)}`}
              >
                <TrendingUp className="h-3 w-3" />
                {format(marketPrice)}
              </Button>
            )
          }
        >
          <Input id="price" {...decimal} {...price} onChange={(e) => { void price.onChange(e); amounts.stop() }} />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field id="fee" label={<>Frais ({currency})</>}>
          <Input id="fee" {...decimal} {...fee} onChange={(e) => { void fee.onChange(e); amounts.stop() }} />
        </Field>
        <div className="space-y-1.5">
          <Label htmlFor="total" className={LABEL}>Montant total</Label>
          <Input id="total" {...decimal} value={amounts.input} onChange={(e) => amounts.edit(e.target.value)} onBlur={amounts.stop} />
          <p className="text-[10px] text-muted-foreground">Quantité x Prix + Frais</p>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field id="executed_at" label="Date">
          <Input id="executed_at" type="datetime-local" {...register('executed_at')} />
        </Field>
        <Field id="notes" label="Notes">
          <Input id="notes" placeholder="Notes..." {...register('notes')} />
        </Field>
      </div>
    </>
  )
}
