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
  notes: z.string().max(500).optional(),
})

type FormData = z.infer<typeof schema>

interface Asset {
  id: string
  symbol: string
  name: string
  portfolio_id: string
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
    queryKey: ['portfolios'],
    queryFn: () => portfoliosApi.list(),
  })

  const { data: assets } = useQuery<Asset[]>({
    queryKey: ['assets'],
    queryFn: () => assetsApi.list(),
  })

  const [selectedPortfolioId, setSelectedPortfolioId] = useState('')
  const [showNewAsset, setShowNewAsset] = useState(false)
  const [newSymbol, setNewSymbol] = useState('')
  const [newName, setNewName] = useState('')
  const [newAssetType, setNewAssetType] = useState('crypto')

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

  const createAssetMutation = useMutation({
    mutationFn: (data: { portfolio_id: string; symbol: string; name: string; asset_type: string }) =>
      assetsApi.create(data),
    onSuccess: (newAsset: Asset) => {
      queryClient.invalidateQueries({ queryKey: ['assets'] })
      setValue('asset_id', newAsset.id)
      setShowNewAsset(false)
      setNewSymbol('')
      setNewName('')
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
    if (!newSymbol.trim() || !selectedPortfolioId) return
    createAssetMutation.mutate({
      portfolio_id: selectedPortfolioId,
      symbol: newSymbol.trim().toUpperCase(),
      name: newName.trim() || newSymbol.trim().toUpperCase(),
      asset_type: newAssetType,
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

        {selectedPortfolioId && !showNewAsset && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="asset_id">Actif *</Label>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-auto py-0 px-1 text-xs text-primary"
                onClick={() => setShowNewAsset(true)}
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
                <SelectValue placeholder={filteredAssets.length ? "Sélectionner un actif" : "Aucun actif — créez-en un"} />
              </SelectTrigger>
              <SelectContent>
                {filteredAssets.map((asset) => (
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
            <Button
              type="button"
              size="sm"
              className="w-full"
              disabled={!newSymbol.trim() || createAssetMutation.isPending}
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
        <DialogContent className="max-w-lg">
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
