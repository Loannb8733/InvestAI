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
  Coins,
  TrendingUp,
  Wallet,
} from 'lucide-react'
import { invalidateAllFinancialData } from '@/lib/invalidate-queries'
import { queryKeys } from '@/lib/queryKeys'
import { PlatformSelect } from '@/components/forms/PlatformSelect'
import { useRealtimePrices } from '@/hooks/useRealtimePrices'
import { cn } from '@/lib/utils'

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
  { value: 'buy', label: 'Achat', shortLabel: 'Achat', icon: ArrowDownRight, color: 'text-green-500', bg: 'bg-green-500/10 border-green-500/20', activeBg: 'bg-green-500/20 border-green-500/40 ring-1 ring-green-500/30' },
  { value: 'sell', label: 'Vente', shortLabel: 'Vente', icon: ArrowUpRight, color: 'text-red-500', bg: 'bg-red-500/10 border-red-500/20', activeBg: 'bg-red-500/20 border-red-500/40 ring-1 ring-red-500/30' },
  { value: 'transfer_in', label: 'Transfert entrant', shortLabel: 'Transfert In', icon: ArrowDownRight, color: 'text-blue-500', bg: 'bg-blue-500/10 border-blue-500/20', activeBg: 'bg-blue-500/20 border-blue-500/40 ring-1 ring-blue-500/30' },
  { value: 'transfer_out', label: 'Transfert sortant', shortLabel: 'Transfert Out', icon: ArrowUpRight, color: 'text-orange-500', bg: 'bg-orange-500/10 border-orange-500/20', activeBg: 'bg-orange-500/20 border-orange-500/40 ring-1 ring-orange-500/30' },
  { value: 'staking_reward', label: 'Récompense staking', shortLabel: 'Staking', icon: Coins, color: 'text-yellow-500', bg: 'bg-yellow-500/10 border-yellow-500/20', activeBg: 'bg-yellow-500/20 border-yellow-500/40 ring-1 ring-yellow-500/30' },
  { value: 'airdrop', label: 'Airdrop', shortLabel: 'Airdrop', icon: Gift, color: 'text-pink-500', bg: 'bg-pink-500/10 border-pink-500/20', activeBg: 'bg-pink-500/20 border-pink-500/40 ring-1 ring-pink-500/30' },
  { value: 'conversion_in', label: 'Conversion entrante', shortLabel: 'Conv. In', icon: ArrowLeftRight, color: 'text-teal-500', bg: 'bg-teal-500/10 border-teal-500/20', activeBg: 'bg-teal-500/20 border-teal-500/40 ring-1 ring-teal-500/30' },
  { value: 'conversion_out', label: 'Conversion sortante', shortLabel: 'Conv. Out', icon: ArrowLeftRight, color: 'text-amber-500', bg: 'bg-amber-500/10 border-amber-500/20', activeBg: 'bg-amber-500/20 border-amber-500/40 ring-1 ring-amber-500/30' },
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
const fmtQty = (v: number, symbol: string) => {
  const str = v.toFixed(8).replace(/\.?0+$/, '')
  return `${str} ${symbol}`
}

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
  const [destinationExchange, setDestinationExchange] = useState('')

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

  const selectedAsset = useMemo(
    () => assets?.find((a) => a.id === selectedAssetId),
    [assets, selectedAssetId],
  )

  // Auto-set platform when asset is selected
  useEffect(() => {
    if (selectedAsset?.exchange) {
      setValue('exchange', selectedAsset.exchange)
    }
  }, [selectedAsset?.exchange, setValue])

  // Real-time price for selected asset
  const symbolsToWatch = useMemo(
    () => (selectedAsset?.symbol ? [selectedAsset.symbol] : []),
    [selectedAsset?.symbol],
  )
  const { prices: realtimePrices } = useRealtimePrices(symbolsToWatch)
  const currentMarketPrice = selectedAsset?.symbol
    ? realtimePrices[selectedAsset.symbol]?.price ?? undefined
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

  const handleQuantityBlur = () => setEditingTotal(false)
  const handleTotalBlur = () => setEditingTotal(false)

  const handleFetchCurrentPrice = () => {
    if (currentMarketPrice != null && currentMarketPrice > 0) {
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
      setDestinationExchange('')
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
      destination_exchange: data.transaction_type === 'transfer_out' && destinationExchange
        ? destinationExchange
        : undefined,
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
      <div className="space-y-4 py-3">
        {/* 1. Transaction Type — Toggle Group */}
        <div className="space-y-2">
          <Label className="text-xs text-muted-foreground uppercase tracking-wider">Type de transaction</Label>
          <div className="grid grid-cols-4 gap-1.5">
            {transactionTypes.map((type) => {
              const Icon = type.icon
              const isActive = transactionType === type.value
              return (
                <button
                  key={type.value}
                  type="button"
                  onClick={() => setValue('transaction_type', type.value as FormData['transaction_type'])}
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

        {/* 2. Portfolio */}
        <div className="space-y-2">
          <Label className="text-xs text-muted-foreground uppercase tracking-wider">Portefeuille</Label>
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

        {/* 3. Asset */}
        {selectedPortfolioId && !showNewAsset && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label className="text-xs text-muted-foreground uppercase tracking-wider">Actif</Label>
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
                    {asset.symbol}{asset.exchange ? ` (${asset.exchange})` : ''}{asset.name && asset.name !== asset.symbol ? ` - ${asset.name}` : ''}
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
          <div className="space-y-3 rounded-lg border border-white/[0.08] bg-white/[0.02] p-3">
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
                  showTrustBadge
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

        {/* 4. Platform */}
        <div className="space-y-2">
          <Label className="text-xs text-muted-foreground uppercase tracking-wider">
            {transactionType === 'transfer_in'
              ? 'Sur (plateforme de réception)'
              : transactionType === 'transfer_out'
                ? 'Depuis (plateforme source)'
                : 'Plateforme'}
          </Label>
          <PlatformSelect
            value={watch('exchange') || ''}
            onChange={(value) => setValue('exchange', value)}
            showTrustBadge
          />
          {transactionType === 'transfer_in' && (
            <p className="text-[10px] text-muted-foreground">
              Plateforme où l'actif est reçu (ex: Tangem, Ledger...)
            </p>
          )}
        </div>

        {/* 4b. Destination platform for transfer_out */}
        {transactionType === 'transfer_out' && (
          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground uppercase tracking-wider">Vers (plateforme destination)</Label>
            <PlatformSelect
              value={destinationExchange}
              onChange={setDestinationExchange}
              placeholder="Cold wallet, autre exchange..."
              showTrustBadge
            />
            <p className="text-[10px] text-muted-foreground">
              Un transfert entrant sera créé automatiquement sur la destination
            </p>
          </div>
        )}

        {/* 5. Quantity + Unit price — 2-column grid */}
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="quantity" className="text-xs text-muted-foreground uppercase tracking-wider">Quantité</Label>
            <Input
              id="quantity"
              type="text"
              inputMode="decimal"
              placeholder="0.00"
              {...register('quantity')}
              onBlur={handleQuantityBlur}
            />
            {errors.quantity && (
              <p className="text-xs text-destructive">{errors.quantity.message}</p>
            )}
          </div>
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="price" className="text-xs text-muted-foreground uppercase tracking-wider">Prix unitaire</Label>
              {currentMarketPrice != null && currentMarketPrice > 0 && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-auto py-0 px-1 text-[10px] text-primary gap-1"
                  onClick={handleFetchCurrentPrice}
                  title={`Prix actuel: ${fmt.format(currentMarketPrice)}`}
                >
                  <TrendingUp className="h-3 w-3" />
                  {fmt.format(currentMarketPrice)}
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
              <p className="text-xs text-destructive">{errors.price.message}</p>
            )}
          </div>
        </div>

        {/* 6. Fees + Total (bidirectional) — 2-column grid */}
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="fee" className="text-xs text-muted-foreground uppercase tracking-wider">Frais (EUR)</Label>
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
          <div className="space-y-1.5">
            <Label htmlFor="total" className="text-xs text-muted-foreground uppercase tracking-wider">Montant total</Label>
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

        {/* 7. Date + Notes — 2-column grid */}
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="executed_at" className="text-xs text-muted-foreground uppercase tracking-wider">Date</Label>
            <Input
              id="executed_at"
              type="datetime-local"
              {...register('executed_at')}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="notes" className="text-xs text-muted-foreground uppercase tracking-wider">Notes</Label>
            <Input
              id="notes"
              placeholder="Notes..."
              {...register('notes')}
            />
          </div>
        </div>

        {/* 8. Impact Summary */}
        {selectedAsset && quantity > 0 && (
          <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] backdrop-blur-sm p-3 space-y-2">
            <div className="flex items-center gap-1.5">
              <Wallet className="h-3.5 w-3.5 text-muted-foreground" />
              <p className="text-xs font-medium text-muted-foreground">Résumé de l'impact</p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-0.5">
                <p className="text-[10px] text-muted-foreground">Nouveau solde</p>
                <p className="text-sm font-semibold">
                  {fmtQty(toNum(newQuantity), selectedAsset.symbol)}
                </p>
              </div>
              {total > 0 && (
                <div className="space-y-0.5 text-right">
                  <p className="text-[10px] text-muted-foreground">
                    {isInbound ? 'Impact Cash' : 'Montant récupéré'}
                  </p>
                  <p className={cn(
                    'text-sm font-semibold',
                    isInbound ? 'text-red-400' : 'text-green-400',
                  )}>
                    {isInbound ? '-' : '+'}{fmt.format(total)}
                  </p>
                </div>
              )}
            </div>
            {!isInbound && newQuantity < 0 && (
              <p className="text-xs text-destructive font-medium">Attention : solde négatif après transaction</p>
            )}
          </div>
        )}
      </div>

      {/* Submit */}
      <div className="flex justify-end gap-2 pt-2">
        <Button type="submit" disabled={mutation.isPending || !selectedAssetId} size="lg">
          {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {typeConfig && <typeConfig.icon className={cn('mr-2 h-4 w-4', typeConfig.color)} />}
          {typeConfig?.label || 'Ajouter'}
        </Button>
      </div>
    </form>
  )

  if (open !== undefined && onOpenChange !== undefined) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="border-white/[0.08] bg-background/80 backdrop-blur-xl shadow-2xl">
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
