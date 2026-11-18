import { useCallback, useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { usePortfolioList } from '@/features/portfolio/hooks'
import { useRealtimePrices } from '@/hooks/useRealtimePrices'
import { queryKeys } from '@/lib/queryKeys'
import { cn, formatCurrency } from '@/lib/utils'
import { apiClient } from '@/shared/api/client'
import { useAuthStore } from '@/stores/authStore'
import { addSchema, toNum, type AddInput, type AddOutput } from '../addSchema'
import { assetBody, EMPTY_ASSET_DRAFT } from '../assetDraft'
import { useCreateAsset, useCreateTransaction } from '../hooks'
import { findTypeButton, MOVEMENT_BUTTONS } from '../typeButtons'
import AssetPicker from './AssetPicker'
import ImpactSummary from './ImpactSummary'
import NewAssetPanel from './NewAssetPanel'
import TransactionFields from './TransactionFields'
import TypeToggle from './TypeToggle'
import { useTotalInput } from '../useTotalInput'

interface AddTransactionFormProps {
  onSuccess?: () => void
  assetId?: string
  assetSymbol?: string
  open?: boolean
  onOpenChange?: (open: boolean) => void
}

export default function AddTransactionForm({ onSuccess, assetId, assetSymbol, open, onOpenChange }: AddTransactionFormProps) {
  const currency = useAuthStore((s) => s.user?.preferredCurrency ?? 'EUR')
  const fmt = useCallback((v: number) => formatCurrency(v, currency), [currency])
  const { data: portfolios } = usePortfolioList()
  const { data: assets } = useQuery({ queryKey: queryKeys.assets.list(), queryFn: () => apiClient.get('/assets') })
  const [portfolioId, setPortfolioId] = useState('')
  const [showNewAsset, setShowNewAsset] = useState(false)
  const [assetDraft, setAssetDraft] = useState(EMPTY_ASSET_DRAFT)
  const [destination, setDestination] = useState('')

  const form = useForm<AddInput, unknown, AddOutput>({
    resolver: zodResolver(addSchema),
    defaultValues: { asset_id: assetId || '', transaction_type: 'buy', quantity: 0, price: 0, fee: 0 },
  })
  const { handleSubmit, reset, setValue, watch, formState } = form
  const amounts = useTotalInput(form)
  const { quantity, total } = amounts
  const type = watch('transaction_type')
  const selectedAssetId = watch('asset_id')
  const portfolioAssets = useMemo(() => (assets && portfolioId ? assets.filter((a) => a.portfolio_id === portfolioId) : []), [assets, portfolioId])
  const selectedAsset = useMemo(() => assets?.find((a) => a.id === selectedAssetId), [assets, selectedAssetId])

  useEffect(() => {
    if (selectedAsset?.exchange) setValue('exchange', selectedAsset.exchange)
  }, [selectedAsset?.exchange, setValue])

  const watched = useMemo(() => (selectedAsset?.symbol ? [selectedAsset.symbol.toUpperCase()] : []), [selectedAsset?.symbol])
  const { prices } = useRealtimePrices(watched, currency)
  const marketPrice = selectedAsset?.symbol ? (prices[selectedAsset.symbol.toUpperCase()]?.price ?? undefined) : undefined

  const createAsset = useCreateAsset((asset) => {
    setValue('asset_id', asset.id)
    setShowNewAsset(false)
    setAssetDraft((d) => ({ ...EMPTY_ASSET_DRAFT, type: d.type }))
  })
  const create = useCreateTransaction(() => {
    reset()
    setPortfolioId('')
    amounts.clear()
    setDestination('')
    onSuccess?.()
  })

  const submit = (data: AddOutput) =>
    create.mutate({
      ...data,
      executed_at: data.executed_at || undefined,
      notes: data.notes || undefined,
      exchange: data.exchange || undefined,
      destination_exchange: data.transaction_type === 'transfer_out' && destination ? destination : undefined,
    })

  const typeConfig = findTypeButton(MOVEMENT_BUTTONS, type)

  const formContent = (
    <form onSubmit={handleSubmit(submit)}>
      <div className="space-y-4 py-3">
        <TypeToggle buttons={MOVEMENT_BUTTONS} value={type} onChange={(value) => setValue('transaction_type', value as AddOutput['transaction_type'])} />
        <AssetPicker
          portfolios={portfolios ?? []}
          portfolioId={portfolioId}
          onPortfolioChange={(value) => {
            setPortfolioId(value)
            setValue('asset_id', '')
            setValue('exchange', '')
            setShowNewAsset(false)
          }}
          assets={portfolioId && !showNewAsset ? portfolioAssets : null}
          assetId={selectedAssetId}
          onAssetChange={(value) => setValue('asset_id', value)}
          onNewAsset={() => {
            setShowNewAsset(true)
            setAssetDraft((d) => ({ ...d, exchange: watch('exchange') || '' }))
          }}
          error={formState.errors.asset_id?.message}
        />
        {portfolioId && showNewAsset && (
          <NewAssetPanel
            draft={assetDraft}
            onChange={setAssetDraft}
            pending={createAsset.isPending}
            onCreate={() => {
              const body = assetBody(assetDraft, portfolioId)
              if (body) createAsset.mutate(body)
            }}
            onCancel={() => setShowNewAsset(false)}
          />
        )}
        <TransactionFields
          form={form}
          type={type}
          currency={currency}
          amounts={amounts}
          marketPrice={marketPrice}
          format={fmt}
          destination={destination}
          onDestinationChange={setDestination}
        />
        {selectedAsset && quantity > 0 && (
          <ImpactSummary type={type} symbol={selectedAsset.symbol} held={toNum(selectedAsset.quantity)} quantity={quantity} total={total} format={fmt} />
        )}
      </div>
      <div className="flex justify-end gap-2 pt-2">
        <Button type="submit" disabled={create.isPending || !selectedAssetId} size="lg" className={cn('text-white transition-colors', typeConfig?.submitBg)}>
          {create.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {typeConfig && <typeConfig.icon className="mr-2 h-4 w-4" />}
          {typeConfig?.label || 'Ajouter'}
        </Button>
      </div>
    </form>
  )

  if (open !== undefined && onOpenChange !== undefined) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="border-border bg-background/80 shadow-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {typeConfig && <typeConfig.icon className={cn('h-5 w-5', typeConfig.color)} />}
              {assetSymbol ? `Transaction ${assetSymbol}` : 'Nouvelle transaction'}
            </DialogTitle>
          </DialogHeader>
          {formContent}
        </DialogContent>
      </Dialog>
    )
  }

  return formContent
}
