import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
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

const assetFormSchema = z.object({
  asset_type: z.string().min(1),
  symbol: z.string().optional(),
  name: z.string().optional(),
  quantity: z.coerce.number().optional(),
  avg_buy_price: z.coerce.number().optional(),
  exchange: z.string().optional(),
  project_name: z.string().optional(),
  invested_amount: z.coerce.number().optional(),
  interest_rate: z.coerce.number().optional(),
  maturity_date: z.string().optional(),
  currency: z.string().default('EUR'),
}).superRefine((data, ctx) => {
  if (data.asset_type === 'real_estate') {
    if (!data.project_name?.trim()) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'Nom du projet requis', path: ['project_name'] })
    }
    if (!data.invested_amount || data.invested_amount <= 0) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'Montant doit être supérieur à 0', path: ['invested_amount'] })
    }
  } else {
    if (!data.symbol?.trim()) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'Symbole requis', path: ['symbol'] })
    }
    if (data.quantity === undefined || data.quantity < 0) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'Quantité invalide (≥ 0)', path: ['quantity'] })
    }
    if (data.avg_buy_price === undefined || data.avg_buy_price < 0) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'Prix invalide (≥ 0)', path: ['avg_buy_price'] })
    }
  }
})

type AssetFormData = z.infer<typeof assetFormSchema>

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
  } = useForm<AssetFormData>({
    resolver: zodResolver(assetFormSchema),
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

  const onSubmit = (data: AssetFormData) => {
    if (isCrowdfunding) {
      const projectName = data.project_name!
      const investedAmount = data.invested_amount!
      const symbol = projectName
        .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
        .toUpperCase()
        .replace(/[^A-Z0-9]+/g, '-')
        .replace(/^-|-$/g, '')
        .substring(0, 20)

      mutation.mutate({
        portfolio_id: portfolioId,
        symbol,
        name: projectName,
        asset_type: 'real_estate',
        quantity: 1,
        avg_buy_price: investedAmount,
        currency: 'EUR',
        exchange: data.exchange || undefined,
        invested_amount: investedAmount,
        interest_rate: data.interest_rate || undefined,
        maturity_date: data.maturity_date || undefined,
        project_status: 'active',
      })
    } else {
      mutation.mutate({
        portfolio_id: portfolioId,
        symbol: data.symbol!.toUpperCase(),
        name: data.name || undefined,
        asset_type: data.asset_type,
        quantity: data.quantity ?? 0,
        avg_buy_price: data.avg_buy_price ?? 0,
        currency: 'EUR',
        exchange: data.exchange || undefined,
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
                  {errors.project_name && (
                    <p className="text-sm text-destructive">{errors.project_name.message}</p>
                  )}
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
                    {errors.invested_amount && (
                      <p className="text-sm text-destructive">{errors.invested_amount.message}</p>
                    )}
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
