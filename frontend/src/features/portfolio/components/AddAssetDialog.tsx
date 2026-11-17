import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import {
  ASSET_FORM_DEFAULTS,
  ASSET_TYPES,
  assetBody,
  assetFormSchema,
  type AssetFormData,
  type AssetFormInput,
} from '../assetForm'
import { useCreateAsset } from '../hooks'
import { MarketAssetFields, RealEstateFields } from './AssetFields'

interface AddAssetDialogProps {
  onOpenChange: (open: boolean) => void
  portfolioId: string
  portfolioName: string
}

export default function AddAssetDialog({ onOpenChange, portfolioId, portfolioName }: AddAssetDialogProps) {
  const {
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
    formState: { errors },
  } = useForm<AssetFormInput, unknown, AssetFormData>({
    resolver: zodResolver(assetFormSchema),
    defaultValues: ASSET_FORM_DEFAULTS,
  })

  const assetType = watch('asset_type')
  const fields = {
    register,
    errors,
    exchange: watch('exchange') || '',
    onExchangeChange: (value: string | undefined) => setValue('exchange', value),
  }
  const mutation = useCreateAsset(() => {
    reset()
    onOpenChange(false)
  })

  const chooseType = (value: string) => {
    const type = ASSET_TYPES.find((t) => t.value === value)
    if (type) setValue('asset_type', type.value)
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Ajouter un actif</DialogTitle>
          <DialogDescription>Ajoutez un nouvel actif au portefeuille "{portfolioName}".</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit((data) => mutation.mutate(assetBody(data, portfolioId)))}>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="asset_type">Type d'actif</Label>
              <Select value={assetType} onValueChange={chooseType}>
                <SelectTrigger>
                  <SelectValue placeholder="Sélectionner un type" />
                </SelectTrigger>
                <SelectContent>
                  {ASSET_TYPES.map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      {type.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {assetType === 'real_estate' ? (
              <RealEstateFields {...fields} />
            ) : (
              <MarketAssetFields {...fields} assetType={assetType} />
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
