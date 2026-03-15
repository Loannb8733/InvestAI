import { useMemo, useState } from 'react'
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
import { Loader2, Plus } from 'lucide-react'
import { invalidateAllFinancialData } from '@/lib/invalidate-queries'
import { queryKeys } from '@/lib/queryKeys'
import { PlatformSelect } from '@/components/forms/PlatformSelect'

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
  { value: 'buy', label: 'Achat' },
  { value: 'sell', label: 'Vente' },
  { value: 'transfer_in', label: 'Transfert entrant' },
  { value: 'transfer_out', label: 'Transfert sortant' },
  { value: 'staking_reward', label: 'Récompense staking' },
  { value: 'airdrop', label: 'Airdrop' },
  { value: 'conversion_in', label: 'Conversion entrante' },
  { value: 'conversion_out', label: 'Conversion sortante' },
]

const assetTypes = [
  { value: 'crypto', label: 'Crypto' },
  { value: 'stock', label: 'Action' },
  { value: 'etf', label: 'ETF' },
  { value: 'real_estate', label: 'Immobilier' },
  { value: 'bond', label: 'Obligation' },
  { value: 'fiat', label: 'Fiat' },
]

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
  // Crowdfunding-specific state
  const [newInvestedAmount, setNewInvestedAmount] = useState('')
  const [newInterestRate, setNewInterestRate] = useState('')
  const [newMaturityDate, setNewMaturityDate] = useState('')

  const [selectedExchange, setSelectedExchange] = useState('')

  const filteredAssets = useMemo(() => {
    if (!assets || !selectedPortfolioId) return []
    return assets.filter((a) => a.portfolio_id === selectedPortfolioId)
  }, [assets, selectedPortfolioId])

  const availableExchanges = useMemo(() => {
    const exchanges = new Set(filteredAssets.map((a) => a.exchange || 'Autre'))
    return Array.from(exchanges).sort()
  }, [filteredAssets])

  const exchangeFilteredAssets = useMemo(() => {
    if (!selectedExchange || selectedExchange === '__all__') return filteredAssets
    return filteredAssets.filter((a) => (a.exchange || 'Autre') === selectedExchange)
  }, [filteredAssets, selectedExchange])

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
      onSuccess?.()
    },
    onError: (error: unknown) => {
      const axiosError = error as import('axios').AxiosError<{ detail?: string }>
      toast({
        variant: 'destructive',
        title: 'Erreur',
        description: axiosError.response?.data?.detail || 'Impossible d\'ajouter la transaction.',
      })
    },
  })

  const onSubmit = (data: FormData) => {
    mutation.mutate(data)
  }

  const handleCreateAsset = () => {
    const isRealEstate = newAssetType === 'real_estate'
    if (isRealEstate) {
      if (!newName.trim() || !selectedPortfolioId || !newInvestedAmount) return
    } else {
      if (!newSymbol.trim() || !selectedPortfolioId) return
    }
    const exchange = newAssetExchange || (selectedExchange && selectedExchange !== '__all__' ? selectedExchange : '')

    // For real estate: auto-generate symbol from name
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

  const transactionType = watch('transaction_type')
  const selectedAssetId = watch('asset_id')
  const toNum = (v: unknown) => { const n = Number(v); return isNaN(n) ? 0 : n }
  const quantity = toNum(watch('quantity'))
  const price = toNum(watch('price'))
  const fee = toNum(watch('fee'))
  const total = quantity * price + fee

  const formContent = (
    <form onSubmit={handleSubmit(onSubmit)}>
      <div className="space-y-4 py-4">
        <div className="space-y-2">
          <Label>Portefeuille *</Label>
          <Select
            value={selectedPortfolioId}
            onValueChange={(value) => {
              setSelectedPortfolioId(value)
              setSelectedExchange('')
              setValue('asset_id', '')
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

        {selectedPortfolioId && (
          <div className="space-y-2">
            <Label>Plateforme</Label>
            <Select
              value={selectedExchange}
              onValueChange={(value) => {
                setSelectedExchange(value)
                setValue('asset_id', '')
                setShowNewAsset(false)
              }}
            >
              <SelectTrigger>
                <SelectValue placeholder="Toutes les plateformes" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">Toutes les plateformes</SelectItem>
                {availableExchanges.map((ex) => (
                  <SelectItem key={ex} value={ex}>{ex}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

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
                  setNewAssetExchange(selectedExchange && selectedExchange !== '__all__' ? selectedExchange : '')
                }}
              >
                <Plus className="h-3 w-3 mr-1" />
                Nouvel actif
              </Button>
            </div>
            <Select
              value={selectedAssetId}
              onValueChange={(value) => setValue('asset_id', value)}
            >
              <SelectTrigger>
                <SelectValue placeholder={exchangeFilteredAssets.length ? "Sélectionner un actif" : "Aucun actif — créez-en un"} />
              </SelectTrigger>
              <SelectContent>
                {exchangeFilteredAssets
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
                <Input
                  placeholder={newAssetType === 'real_estate' ? 'Tokimo...' : 'Bitstamp, Binance...'}
                  value={newAssetExchange}
                  onChange={(e) => setNewAssetExchange(e.target.value)}
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
              Créer l'actif
            </Button>
          </div>
        )}

        <div className="space-y-2">
          <Label htmlFor="transaction_type">Type de transaction</Label>
          <Select
            value={transactionType}
            onValueChange={(value) => setValue('transaction_type', value as FormData['transaction_type'])}
          >
            <SelectTrigger>
              <SelectValue placeholder="Sélectionner un type" />
            </SelectTrigger>
            <SelectContent>
              {transactionTypes.map((type) => (
                <SelectItem key={type.value} value={type.value}>
                  {type.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="quantity">Quantité</Label>
            <Input
              id="quantity"
              type="text"
              inputMode="decimal"
              placeholder="0.00"
              {...register('quantity')}
            />
            {errors.quantity && (
              <p className="text-sm text-destructive">{errors.quantity.message}</p>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="price">Prix unitaire (EUR)</Label>
            <Input
              id="price"
              type="text"
              inputMode="decimal"
              placeholder="0.00"
              {...register('price')}
            />
            {errors.price && (
              <p className="text-sm text-destructive">{errors.price.message}</p>
            )}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="fee">Frais (EUR)</Label>
            <Input
              id="fee"
              type="text"
              inputMode="decimal"
              placeholder="0.00"
              {...register('fee')}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="executed_at">Date (optionnel)</Label>
            <Input
              id="executed_at"
              type="datetime-local"
              {...register('executed_at')}
            />
          </div>
        </div>

        {(transactionType === 'transfer_in' || transactionType === 'transfer_out') && (
          <div className="space-y-2">
            <Label htmlFor="exchange">
              {transactionType === 'transfer_in' ? 'Depuis (plateforme source)' : 'Vers (plateforme destination)'}
            </Label>
            <PlatformSelect
              value={watch('exchange') || ''}
              onChange={(value) => setValue('exchange', value)}
            />
          </div>
        )}

        <div className="space-y-2">
          <Label htmlFor="notes">Notes (optionnel)</Label>
          <Input
            id="notes"
            placeholder="Notes sur la transaction..."
            {...register('notes')}
          />
        </div>

        <div className="rounded-lg bg-muted p-3">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Total:</span>
            <span className="font-medium">
              {new Intl.NumberFormat('fr-FR', {
                style: 'currency',
                currency: 'EUR',
              }).format(total)}
            </span>
          </div>
        </div>
      </div>
      <div className="flex justify-end gap-2">
        <Button type="submit" disabled={mutation.isPending || !selectedAssetId}>
          {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Ajouter
        </Button>
      </div>
    </form>
  )

  // If open/onOpenChange props are provided, wrap in Dialog
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

  // Otherwise, render form directly
  return formContent
}
