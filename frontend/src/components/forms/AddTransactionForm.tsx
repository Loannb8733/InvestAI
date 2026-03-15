import { useCallback, useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
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
import { useToast } from '@/hooks/use-toast'
import { transactionsApi, assetsApi, portfoliosApi } from '@/services/api'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  ArrowDownRight,
  ArrowLeftRight,
  ArrowUpRight,
  Gift,
  Loader2,
  Plus,
  RefreshCw,
  Coins,
} from 'lucide-react'
import { invalidateAllFinancialData } from '@/lib/invalidate-queries'
import { queryKeys } from '@/lib/queryKeys'
import { PlatformSelect } from '@/components/forms/PlatformSelect'
import { useRealtimePrices } from '@/hooks/useRealtimePrices'

const schema = z.object({
  asset_id: z.string().min(1, 'Sélectionnez un actif'),
  transaction_type: z.enum([
    'buy',
    'sell',
    'transfer_in',
    'transfer_out',
    'staking_reward',
    'airdrop',
    'conversion_in',
    'conversion_out',
  ]),
  quantity: z.coerce.number().positive('Quantité doit être positive'),
  price: z.coerce.number().min(0, 'Prix invalide'),
  fee: z.coerce.number().min(0).default(0),
  executed_at: z.string().optional(),
  exchange: z.string().max(50).optional(),
  notes: z.string().max(500).optional(),
})

type FormData = z.infer<typeof schema>

interface Asset {
  id: string
  symbol: string
  name: string
  portfolio_id: string
  exchange?: string
  quantity?: number
  asset_type?: string
}

interface Portfolio {
  id: string
  name: string
}

interface AddTransactionFormProps {
  onSuccess?: () => void
  assetId?: string
  assetSymbol?: string
  open?: boolean
  onOpenChange?: (open: boolean) => void
}

const transactionTypes = [
  { value: 'buy', label: 'Achat', icon: ArrowDownRight, color: 'text-green-500' },
  { value: 'sell', label: 'Vente', icon: ArrowUpRight, color: 'text-red-500' },
  { value: 'transfer_in', label: 'Transfert entrant', icon: ArrowDownRight, color: 'text-blue-500' },
  { value: 'transfer_out', label: 'Transfert sortant', icon: ArrowUpRight, color: 'text-orange-500' },
  { value: 'staking_reward', label: 'Récompense staking', icon: Coins, color: 'text-yellow-500' },
  { value: 'airdrop', label: 'Airdrop', icon: Gift, color: 'text-pink-500' },
  { value: 'conversion_in', label: 'Conversion entrante', icon: ArrowLeftRight, color: 'text-teal-500' },
  { value: 'conversion_out', label: 'Conversion sortante', icon: ArrowLeftRight, color: 'text-amber-500' },
] as const

const assetTypes = [
  { value: 'crypto', label: 'Crypto' },
  { value: 'stock', label: 'Action' },
  { value: 'etf', label: 'ETF' },
  { value: 'real_estate', label: 'Immobilier' },
  { value: 'bond', label: 'Obligation' },
  { value: 'fiat', label: 'Fiat' },
]

const fmt = new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' })

export default function AddTransactionForm({
  onSuccess,
  assetId,
  assetSymbol,
  open,
  onOpenChange,
}: AddTransactionFormProps) {
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const { data: portfolios } = useQuery<Portfolio[]>({
    queryKey: queryKeys.portfolios.list(),
    queryFn: () => portfoliosApi.list(),
    staleTime: 60_000,
  })

  const { data: assets } = useQuery<Asset[]>({
    queryKey: queryKeys.assets.list(),
    queryFn: () => assetsApi.list(),
  })

  const [selectedPortfolioId, setSelectedPortfolioId] = useState('')
  const [showNewAsset, setShowNewAsset] = useState(false)
  const [newSymbol, setNewSymbol] = useState('')
  const [newName, setNewName] = useState('')
  const [newAssetType, setNewAssetType] = useState('crypto')
  const [newAssetExchange, setNewAssetExchange] = useState('')
  const [newInvestedAmount, setNewInvestedAmount] = useState('')
  const [newInterestRate, setNewInterestRate] = useState('')
  const [newMaturityDate, setNewMaturityDate] = useState('')
  const [totalInput, setTotalInput] = useState('')
  const [editingTotal, setEditingTotal] = useState(false)

  const filteredAssets = useMemo(() => {
    if (!assets || !selectedPortfolioId) return []
    return assets.filter((a) => a.portfolio_id === selectedPortfolioId)
  }, [assets, selectedPortfolioId])

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
    formState: { errors },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      asset_id: assetId || '',
      transaction_type: 'buy',
      quantity: 0,
      price: 0,
      fee: 0,
    },
  })

  const transactionType = watch('transaction_type')
  const selectedAssetId = watch('asset_id')
  const toNum = (v: unknown) => { const n = Number(v); return isNaN(n) ? 0 : n }
  const quantity = toNum(watch('quantity'))
  const price = toNum(watch('price'))
  const fee = toNum(watch('fee'))
  const total = quantity * price + fee

  // Get selected asset details
  const selectedAsset = useMemo(
    () => assets?.find((a) => a.id === selectedAssetId),
    [assets, selectedAssetId],
  )

  // Real-time price for selected asset
  const symbolsToWatch = useMemo(
    () => (selectedAsset?.symbol ? [selectedAsset.symbol] : []),
    [selectedAsset?.symbol],
  )
  const { prices: realtimePrices } = useRealtimePrices(symbolsToWatch)
  const currentMarketPrice = selectedAsset?.symbol
    ? realtimePrices[selectedAsset.symbol]?.price
    : undefined

  // Bidirectional total calculation
  const handleTotalChange = useCallback((rawValue: string) => {
    setTotalInput(rawValue)
    setEditingTotal(true)
    const totalVal = parseFloat(rawValue)
    if (!isNaN(totalVal) && price > 0) {
      const computedQty = Math.max(0, (totalVal - fee) / price)
      setValue('quantity', parseFloat(computedQty.toFixed(8)))
    }
  }, [price, fee, setValue])

  // Sync total display when quantity/price/fee change (unless user is editing total)
  useEffect(() => {
    if (!editingTotal) {
      setTotalInput(total > 0 ? total.toFixed(2) : '')
    }
  }, [total, editingTotal])

  // Reset editingTotal when quantity changes from form
  const handleQuantityBlur = () => setEditingTotal(false)
  const handleTotalBlur = () => setEditingTotal(false)

  const handleFetchCurrentPrice = () => {
    if (currentMarketPrice && currentMarketPrice > 0) {
      setValue('price', parseFloat(currentMarketPrice.toFixed(8)))
      setEditingTotal(false)
    }
  }

  // Post-transaction preview
  const currentQuantity = toNum(selectedAsset?.quantity)
  const isInbound = ['buy', 'transfer_in', 'staking_reward', 'airdrop', 'conversion_in'].includes(transactionType)
  const newQuantity = isInbound
    ? currentQuantity + quantity
    : currentQuantity - quantity

  const typeConfig = transactionTypes.find((t) => t.value === transactionType)

  const createAssetMutation = useMutation({
    mutationFn: (data: Parameters<typeof assetsApi.create>[0]) =>
      assetsApi.create(data),
    onSuccess: (newAsset: Asset) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.assets.all })
      setValue('asset_id', newAsset.id)
      setShowNewAsset(false)
      setNewSymbol('')
      setNewName('')
      setNewAssetExchange('')
      setNewInvestedAmount('')
      setNewInterestRate('')
      setNewMaturityDate('')
      toast({ title: 'Actif créé', description: `${newAsset.symbol} ajouté au portefeuille.` })
    },
    onError: (error: unknown) => {
      const axiosError = error as import('axios').AxiosError<{ detail?: string }>
      toast({
        variant: 'destructive',
        title: 'Erreur',
        description: axiosError.response?.data?.detail || "Impossible de créer l'actif.",
      })
    },
  })

  const mutation = useMutation({
    mutationFn: (data: FormData) =>
      transactionsApi.create({
        ...data,
        asset_id: data.asset_id,
      }),
    onSuccess: () => {
      invalidateAllFinancialData(queryClient)
      toast({
        title: 'Transaction ajoutée',
        description: 'La transaction a été enregistrée.',
      })
      reset()
      setSelectedPortfolioId('')
      setTotalInput('')
      setEditingTotal(false)
      onSuccess?.()
    },
    onError: (error: unknown) => {
      const axiosError = error as import('axios').AxiosError<{ detail?: string | Array<{ msg: string }> }>
      const detail = axiosError.response?.data?.detail
      const message = typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((e) => e.msg).join(', ')
          : 'Impossible d\'ajouter la transaction.'
      toast({
        variant: 'destructive',
        title: 'Erreur',
        description: message,
      })
    },
  })

  const onSubmit = (data: FormData) => {
    const payload = {
      ...data,
      executed_at: data.executed_at || undefined,
      notes: data.notes || undefined,
      exchange: data.exchange || undefined,
    }
    mutation.mutate(payload)
  }

  const handleCreateAsset = () => {
    const isRealEstate = newAssetType === 'real_estate'
    if (isRealEstate) {
      if (!newName.trim() || !selectedPortfolioId || !newInvestedAmount) return
    } else {
      if (!newSymbol.trim() || !selectedPortfolioId) return
    }
    const exchange = newAssetExchange || ''

    const symbol = isRealEstate
      ? newName.trim().substring(0, 18).toUpperCase().replace(/\s+/g, '-')
      : newSymbol.trim().toUpperCase()

    const amount = parseFloat(newInvestedAmount) || 0

    createAssetMutation.mutate({
      portfolio_id: selectedPortfolioId,
      symbol,
      name: newName.trim() || symbol,
      asset_type: newAssetType,
      ...(exchange ? { exchange } : {}),
      ...(isRealEstate
        ? {
            quantity: 1,
            avg_buy_price: amount,
            invested_amount: amount,
            interest_rate: parseFloat(newInterestRate) || undefined,
            maturity_date: newMaturityDate || undefined,
            project_status: 'active',
          }
        : {}),
    })
  }

  const formContent = (
    <form onSubmit={handleSubmit(onSubmit)}>
      <div className="space-y-4 py-4">
        {/* 1. Portfolio */}
        <div className="space-y-2">
          <Label>Portefeuille *</Label>
          <Select
            value={selectedPortfolioId}
            onValueChange={(value) => {
              setSelectedPortfolioId(value)
              setValue('asset_id', '')
              setValue('exchange', '')
              setShowNewAsset(false)
            }}
          >
            <SelectTrigger>
              <SelectValue placeholder="Sélectionner un portefeuille" />
            </SelectTrigger>
            <SelectContent>
              {portfolios?.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* 2. Asset — "J'achète [BTC]..." */}
        {selectedPortfolioId && !showNewAsset && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="asset_id">Actif *</Label>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-auto py-0 px-1 text-xs text-primary"
                onClick={() => {
                  setShowNewAsset(true)
                  setNewAssetExchange(watch('exchange') || '')
                }}
              >
                <Plus className="h-3 w-3 mr-1" />
                Nouvel actif
              </Button>
            </div>
            <Select
              value={selectedAssetId}
              onValueChange={(value) => {
                setValue('asset_id', value)
                const selected = assets?.find((a) => a.id === value)
                if (selected?.exchange) setValue('exchange', selected.exchange)
              }}
            >
              <SelectTrigger>
                <SelectValue placeholder={filteredAssets.length ? "Sélectionner un actif" : "Aucun actif — créez-en un"} />
              </SelectTrigger>
              <SelectContent>
                {filteredAssets
                  .sort((a, b) => a.symbol.localeCompare(b.symbol))
                  .map((asset) => (
                  <SelectItem key={asset.id} value={asset.id}>
                    {asset.symbol} - {asset.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.asset_id && (
              <p className="text-sm text-destructive">{errors.asset_id.message}</p>
            )}
          </div>
        )}

        {/* Inline new asset creation */}
        {selectedPortfolioId && showNewAsset && (
          <div className="space-y-3 rounded-lg border p-3">
            <div className="flex items-center justify-between">
              <Label className="font-medium">Nouvel actif</Label>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-auto py-0 px-1 text-xs"
                onClick={() => setShowNewAsset(false)}
              >
                Annuler
              </Button>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <Label className="text-xs">Type *</Label>
                <Select value={newAssetType} onValueChange={setNewAssetType}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {assetTypes.map((t) => (
                      <SelectItem key={t.value} value={t.value}>
                        {t.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Plateforme *</Label>
                <PlatformSelect
                  value={newAssetExchange}
                  onChange={setNewAssetExchange}
                  placeholder="Plateforme..."
                  showTrustBadge={false}
                />
              </div>
            </div>

            {newAssetType === 'real_estate' ? (
              <>
                <div className="space-y-1">
                  <Label className="text-xs">Nom du projet *</Label>
                  <Input
                    placeholder="Résidence Lyon Centre..."
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                  />
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div className="space-y-1">
                    <Label className="text-xs">Montant investi *</Label>
                    <Input
                      type="number"
                      placeholder="2000"
                      value={newInvestedAmount}
                      onChange={(e) => setNewInvestedAmount(e.target.value)}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Taux annuel (%)</Label>
                    <Input
                      type="number"
                      step="0.1"
                      placeholder="10.5"
                      value={newInterestRate}
                      onChange={(e) => setNewInterestRate(e.target.value)}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Echéance</Label>
                    <Input
                      type="date"
                      value={newMaturityDate}
                      onChange={(e) => setNewMaturityDate(e.target.value)}
                    />
                  </div>
                </div>
              </>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <Label className="text-xs">Symbole *</Label>
                  <Input
                    placeholder="BTC, AAPL..."
                    value={newSymbol}
                    onChange={(e) => setNewSymbol(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Nom</Label>
                  <Input
                    placeholder="Bitcoin, Apple..."
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                  />
                </div>
              </div>
            )}

            <Button
              type="button"
              size="sm"
              className="w-full"
              disabled={
                (newAssetType === 'real_estate'
                  ? !newName.trim() || !newInvestedAmount || !newAssetExchange.trim()
                  : !newSymbol.trim() || !newAssetExchange.trim()) ||
                createAssetMutation.isPending
              }
              onClick={handleCreateAsset}
            >
              {createAssetMutation.isPending && <Loader2 className="mr-2 h-3 w-3 animate-spin" />}
              Créer l&apos;actif
            </Button>
          </div>
        )}

        {/* 3. Platform — "...sur [Binance]" */}
        <div className="space-y-2">
          <Label>
            {transactionType === 'transfer_in'
              ? 'Depuis (plateforme source)'
              : transactionType === 'transfer_out'
                ? 'Vers (plateforme destination)'
                : 'Plateforme'}
          </Label>
          <PlatformSelect
            value={watch('exchange') || ''}
            onChange={(value) => setValue('exchange', value)}
          />
        </div>

        {/* 4. Transaction type with icons */}
        <div className="space-y-2">
          <Label htmlFor="transaction_type">Type de transaction</Label>
          <Select
            value={transactionType}
            onValueChange={(value) => setValue('transaction_type', value as FormData['transaction_type'])}
          >
            <SelectTrigger>
              <SelectValue>
                {typeConfig && (
                  <span className="flex items-center gap-2">
                    <typeConfig.icon className={`h-4 w-4 ${typeConfig.color}`} />
                    {typeConfig.label}
                  </span>
                )}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {transactionTypes.map((type) => {
                const Icon = type.icon
                return (
                  <SelectItem key={type.value} value={type.value}>
                    <span className="flex items-center gap-2">
                      <Icon className={`h-4 w-4 ${type.color}`} />
                      {type.label}
                    </span>
                  </SelectItem>
                )
              })}
            </SelectContent>
          </Select>
        </div>

        {/* 5. Quantity + Unit price (with "Current price" button) */}
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="quantity">Quantité</Label>
            <Input
              id="quantity"
              type="text"
              inputMode="decimal"
              placeholder="0.00"
              {...register('quantity')}
              onBlur={handleQuantityBlur}
            />
            {errors.quantity && (
              <p className="text-sm text-destructive">{errors.quantity.message}</p>
            )}
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="price">Prix unitaire (EUR)</Label>
              {currentMarketPrice !== undefined && currentMarketPrice > 0 && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-auto py-0 px-1 text-xs text-primary"
                  onClick={handleFetchCurrentPrice}
                  title={`Prix actuel: ${fmt.format(currentMarketPrice)}`}
                >
                  <RefreshCw className="h-3 w-3 mr-1" />
                  Prix actuel
                </Button>
              )}
            </div>
            <Input
              id="price"
              type="text"
              inputMode="decimal"
              placeholder="0.00"
              {...register('price')}
              onChange={(e) => {
                register('price').onChange(e)
                setEditingTotal(false)
              }}
            />
            {errors.price && (
              <p className="text-sm text-destructive">{errors.price.message}</p>
            )}
          </div>
        </div>

        {/* 6. Fees + Total (bidirectional) */}
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="fee">Frais (EUR)</Label>
            <Input
              id="fee"
              type="text"
              inputMode="decimal"
              placeholder="0.00"
              {...register('fee')}
              onChange={(e) => {
                register('fee').onChange(e)
                setEditingTotal(false)
              }}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="total">Montant total (EUR)</Label>
            <Input
              id="total"
              type="text"
              inputMode="decimal"
              placeholder="0.00"
              value={totalInput}
              onChange={(e) => handleTotalChange(e.target.value)}
              onBlur={handleTotalBlur}
            />
            <p className="text-[10px] text-muted-foreground">Quantité x Prix + Frais</p>
          </div>
        </div>

        {/* 7. Date + Notes */}
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="executed_at">Date (optionnel)</Label>
            <Input
              id="executed_at"
              type="datetime-local"
              {...register('executed_at')}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="notes">Notes (optionnel)</Label>
            <Input
              id="notes"
              placeholder="Notes..."
              {...register('notes')}
            />
          </div>
        </div>

        {/* 8. Preview zone */}
        {selectedAsset && quantity > 0 && (
          <div className="rounded-lg border border-border/50 bg-muted/50 p-3 space-y-1.5">
            <p className="text-xs font-medium text-muted-foreground">Prévisualisation</p>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">
                Solde {selectedAsset.symbol} après transaction
              </span>
              <span className="font-medium">
                {toNum(newQuantity).toFixed(8).replace(/\.?0+$/, '')} {selectedAsset.symbol}
              </span>
            </div>
            {total > 0 && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">
                  {isInbound ? 'Coût total' : 'Montant récupéré'}
                </span>
                <span className={isInbound ? 'font-medium text-red-400' : 'font-medium text-green-400'}>
                  {isInbound ? '-' : '+'}{fmt.format(total)}
                </span>
              </div>
            )}
            {!isInbound && newQuantity < 0 && (
              <p className="text-xs text-destructive">Attention : solde négatif après transaction</p>
            )}
          </div>
        )}
      </div>

      {/* Submit */}
      <div className="flex justify-end gap-2 pt-2">
        <Button type="submit" disabled={mutation.isPending || !selectedAssetId} size="lg">
          {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {typeConfig && <typeConfig.icon className={`mr-2 h-4 w-4 ${typeConfig.color}`} />}
          {typeConfig?.label || 'Ajouter'}
        </Button>
      </div>
    </form>
  )

  if (open !== undefined && onOpenChange !== undefined) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Ajouter une transaction</DialogTitle>
            <DialogDescription>
              {assetSymbol ? `Transaction pour ${assetSymbol}` : 'Enregistrez une nouvelle transaction'}
            </DialogDescription>
          </DialogHeader>
          {formContent}
        </DialogContent>
      </Dialog>
    )
  }

  return formContent
}
