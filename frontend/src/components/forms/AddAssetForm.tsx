import { useForm } from 'react-hook-form'
import { useMutation, useQueryClient } from '@tanstack/react-query'
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useToast } from '@/hooks/use-toast'
import { assetsApi } from '@/services/api'
import { Loader2 } from 'lucide-react'
import { invalidateAllFinancialData } from '@/lib/invalidate-queries'
import { PlatformSelect } from '@/components/forms/PlatformSelect'

interface AddAssetFormProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  portfolioId: string
  portfolioName: string
}

const assetTypes = [
  { value: 'crypto', label: 'Crypto-monnaie' },
  { value: 'stock', label: 'Action' },
  { value: 'etf', label: 'ETF' },
  { value: 'real_estate', label: 'Immobilier' },
  { value: 'bond', label: 'Obligation' },
  { value: 'other', label: 'Autre' },
]

export default function AddAssetForm({
  open,
  onOpenChange,
  portfolioId,
  portfolioName,
}: AddAssetFormProps) {
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
    formState: { errors },
  } = useForm<Record<string, unknown>>({
    defaultValues: {
      asset_type: 'crypto',
      quantity: 0,
      avg_buy_price: 0,
      currency: 'EUR',
      project_name: '',
      invested_amount: 0,
      interest_rate: 0,
      maturity_date: '',
    },
  })

  const assetType = watch('asset_type') as string
  const isCrowdfunding = assetType === 'real_estate'

  const mutation = useMutation({
    mutationFn: (data: Parameters<typeof assetsApi.create>[0]) =>
      assetsApi.create(data),
    onSuccess: () => {
      invalidateAllFinancialData(queryClient)
      toast({
        title: 'Actif ajouté',
        description: 'L\'actif a été ajouté à votre portefeuille.',
      })
      reset()
      onOpenChange(false)
    },
    onError: (error: unknown) => {
      const axiosError = error as import('axios').AxiosError<{ detail?: string }>
      toast({
        variant: 'destructive',
        title: 'Erreur',
        description: axiosError.response?.data?.detail || 'Impossible d\'ajouter l\'actif.',
      })
    },
  })

  const onSubmit = (data: Record<string, unknown>) => {
    if (isCrowdfunding) {
      const projectName = data.project_name as string
      const investedAmount = Number(data.invested_amount)
      const interestRate = Number(data.interest_rate) || undefined
      const maturityDate = (data.maturity_date as string) || undefined
      const symbol = projectName
        .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
        .toUpperCase()
        .replace(/[^A-Z0-9]+/g, '-')
        .replace(/^-|-$/g, '')
        .substring(0, 20)

      if (!projectName || investedAmount <= 0) {
        toast({ variant: 'destructive', title: 'Erreur', description: 'Nom du projet et montant requis.' })
        return
      }

      mutation.mutate({
        portfolio_id: portfolioId,
        symbol,
        name: projectName,
        asset_type: 'real_estate',
        quantity: 1,
        avg_buy_price: investedAmount,
        currency: 'EUR',
        exchange: (data.exchange as string) || undefined,
        invested_amount: investedAmount,
        interest_rate: interestRate,
        maturity_date: maturityDate,
        project_status: 'active',
      })
    } else {
      const symbol = (data.symbol as string || '').toUpperCase()
      if (!symbol) {
        toast({ variant: 'destructive', title: 'Erreur', description: 'Symbole requis.' })
        return
      }
      mutation.mutate({
        portfolio_id: portfolioId,
        symbol,
        name: (data.name as string) || undefined,
        asset_type: data.asset_type as string,
        quantity: Number(data.quantity),
        avg_buy_price: Number(data.avg_buy_price),
        currency: 'EUR',
        exchange: (data.exchange as string) || undefined,
      })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Ajouter un actif</DialogTitle>
          <DialogDescription>
            Ajoutez un nouvel actif au portefeuille "{portfolioName}".
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)}>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="asset_type">Type d'actif</Label>
              <Select
                value={assetType}
                onValueChange={(value) => setValue('asset_type', value)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Sélectionner un type" />
                </SelectTrigger>
                <SelectContent>
                  {assetTypes.map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      {type.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {isCrowdfunding ? (
              <>
                <div className="space-y-2">
                  <Label htmlFor="project_name">Nom du projet</Label>
                  <Input
                    id="project_name"
                    placeholder="Résidence Lyon, Bureau Paris..."
                    {...register('project_name')}
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="invested_amount">Montant investi (€)</Label>
                    <Input
                      id="invested_amount"
                      type="number"
                      step="any"
                      placeholder="2000"
                      {...register('invested_amount')}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="interest_rate">Taux annuel (%)</Label>
                    <Input
                      id="interest_rate"
                      type="number"
                      step="0.1"
                      placeholder="10.5"
                      {...register('interest_rate')}
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="maturity_date">Date d'échéance</Label>
                  <Input
                    id="maturity_date"
                    type="date"
                    {...register('maturity_date')}
                  />
                </div>

                <div className="space-y-2">
                  <Label>Plateforme</Label>
                  <PlatformSelect
                    value={(watch('exchange') as string) || ''}
                    onChange={(value) => setValue('exchange', value || undefined)}
                    placeholder="Sélectionner une plateforme"
                  />
                </div>
              </>
            ) : (
              <>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="symbol">Symbole</Label>
                    <Input
                      id="symbol"
                      placeholder={assetType === 'crypto' ? 'BTC, ETH...' : 'AAPL, MSFT...'}
                      {...register('symbol')}
                    />
                    {errors.symbol && (
                      <p className="text-sm text-destructive">{errors.symbol?.message as string}</p>
                    )}
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="name">Nom (optionnel)</Label>
                    <Input
                      id="name"
                      placeholder="Bitcoin, Apple..."
                      {...register('name')}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="quantity">Quantité</Label>
                    <Input
                      id="quantity"
                      type="number"
                      step="any"
                      placeholder="0.00"
                      {...register('quantity')}
                    />
                    {errors.quantity && (
                      <p className="text-sm text-destructive">{errors.quantity?.message as string}</p>
                    )}
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="avg_buy_price">Prix moyen d'achat (€)</Label>
                    <Input
                      id="avg_buy_price"
                      type="number"
                      step="any"
                      placeholder="0.00"
                      {...register('avg_buy_price')}
                    />
                    {errors.avg_buy_price && (
                      <p className="text-sm text-destructive">{errors.avg_buy_price?.message as string}</p>
                    )}
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>Plateforme (optionnel)</Label>
                  <PlatformSelect
                    value={(watch('exchange') as string) || ''}
                    onChange={(value) => setValue('exchange', value || undefined)}
                    placeholder="Où est stocké cet actif ?"
                  />
                </div>
              </>
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Annuler
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Ajouter
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
