import type { FieldErrors, UseFormRegister } from 'react-hook-form'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { PlatformSelect } from '@/components/forms/PlatformSelect'
import type { AssetFormInput } from '../assetForm'

interface AssetFieldsProps {
  register: UseFormRegister<AssetFormInput>
  errors: FieldErrors<AssetFormInput>
  exchange: string
  onExchangeChange: (value: string | undefined) => void
}

function FieldError({ message }: { message: string | undefined }) {
  return message ? <p className="text-sm text-destructive">{message}</p> : null
}

export function RealEstateFields({ register, errors, exchange, onExchangeChange }: AssetFieldsProps) {
  return (
    <>
      <div className="space-y-2">
        <Label htmlFor="project_name">Nom du projet</Label>
        <Input id="project_name" placeholder="Résidence Lyon, Bureau Paris..." {...register('project_name')} />
        <FieldError message={errors.project_name?.message} />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="invested_amount">Montant investi (€)</Label>
          <Input id="invested_amount" type="number" step="any" placeholder="2000" {...register('invested_amount')} />
          <FieldError message={errors.invested_amount?.message} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="interest_rate">Taux annuel (%)</Label>
          <Input id="interest_rate" type="number" step="0.1" placeholder="10.5" {...register('interest_rate')} />
        </div>
      </div>
      <div className="space-y-2">
        <Label htmlFor="maturity_date">Date d'échéance</Label>
        <Input id="maturity_date" type="date" {...register('maturity_date')} />
      </div>
      <div className="space-y-2">
        <Label>Plateforme</Label>
        <PlatformSelect
          value={exchange}
          onChange={(value) => onExchangeChange(value || undefined)}
          placeholder="Sélectionner une plateforme"
        />
      </div>
    </>
  )
}

export function MarketAssetFields({ register, errors, exchange, onExchangeChange, assetType }: AssetFieldsProps & { assetType: string }) {
  return (
    <>
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="symbol">Symbole</Label>
          <Input id="symbol" placeholder={assetType === 'crypto' ? 'BTC, ETH...' : 'AAPL, MSFT...'} {...register('symbol')} />
          <FieldError message={errors.symbol?.message} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="name">Nom (optionnel)</Label>
          <Input id="name" placeholder="Bitcoin, Apple..." {...register('name')} />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="quantity">Quantité</Label>
          <Input id="quantity" type="number" step="any" placeholder="0.00" {...register('quantity')} />
          <FieldError message={errors.quantity?.message} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="avg_buy_price">Prix moyen d'achat (€)</Label>
          <Input id="avg_buy_price" type="number" step="any" placeholder="0.00" {...register('avg_buy_price')} />
          <FieldError message={errors.avg_buy_price?.message} />
        </div>
      </div>
      <div className="space-y-2">
        <Label>Plateforme (optionnel)</Label>
        <PlatformSelect
          value={exchange}
          onChange={(value) => onExchangeChange(value || undefined)}
          placeholder="Où est stocké cet actif ?"
        />
      </div>
    </>
  )
}
