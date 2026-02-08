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

const schema = z.object({
  symbol: z.string().min(1, 'Symbole requis').max(20).toUpperCase(),
  name: z.string().max(200).optional(),
  asset_type: z.enum(['crypto', 'stock', 'etf', 'real_estate', 'bond', 'other']),
  quantity: z.coerce.number().min(0, 'Quantité invalide'),
  avg_buy_price: z.coerce.number().min(0, 'Prix invalide'),
  currency: z.string().default('EUR'),
})

type FormData = z.infer<typeof schema>

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
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      asset_type: 'crypto',
      quantity: 0,
      avg_buy_price: 0,
      currency: 'EUR',
    },
  })

  const mutation = useMutation({
    mutationFn: (data: FormData) =>
      assetsApi.create({
        ...data,
        portfolio_id: portfolioId,
      }),
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

  const onSubmit = (data: FormData) => {
    mutation.mutate(data)
  }

  const assetType = watch('asset_type')

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
                onValueChange={(value) => setValue('asset_type', value as FormData['asset_type'])}
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

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="symbol">Symbole</Label>
                <Input
                  id="symbol"
                  placeholder={assetType === 'crypto' ? 'BTC, ETH...' : 'AAPL, MSFT...'}
                  {...register('symbol')}
                />
                {errors.symbol && (
                  <p className="text-sm text-destructive">{errors.symbol.message}</p>
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
                  <p className="text-sm text-destructive">{errors.quantity.message}</p>
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
                  <p className="text-sm text-destructive">{errors.avg_buy_price.message}</p>
                )}
              </div>
            </div>
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
