import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { Schema } from '@/shared/api/client'

type Asset = Schema<'AssetResponse'>

interface AssetPickerProps {
  portfolios: { id: string; name: string }[]
  portfolioId: string
  onPortfolioChange: (id: string) => void
  assets: Asset[] | null
  assetId: string
  onAssetChange: (id: string) => void
  onNewAsset: () => void
  error?: string
}

const LABEL = 'text-xs text-muted-foreground uppercase tracking-wider'

export default function AssetPicker(props: AssetPickerProps) {
  const { portfolios, portfolioId, onPortfolioChange, assets, assetId, onAssetChange, onNewAsset, error } = props
  return (
    <div className="grid grid-cols-2 gap-3">
      <div className="space-y-1.5">
        <Label className={LABEL}>Portefeuille</Label>
        <Select value={portfolioId} onValueChange={onPortfolioChange}>
          <SelectTrigger aria-label="Portefeuille">
            <SelectValue placeholder="Portefeuille..." />
          </SelectTrigger>
          <SelectContent>
            {portfolios.map((p) => (
              <SelectItem key={p.id} value={p.id}>
                {p.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {assets && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label className={LABEL}>Actif</Label>
            <Button type="button" variant="ghost" size="sm" className="h-auto py-0 px-1 text-[10px] text-primary" onClick={onNewAsset}>
              <Plus className="h-3 w-3 mr-0.5" />
              Nouveau
            </Button>
          </div>
          <Select value={assetId} onValueChange={onAssetChange}>
            <SelectTrigger aria-label="Actif">
              <SelectValue placeholder={assets.length ? 'Actif...' : 'Aucun actif'} />
            </SelectTrigger>
            <SelectContent>
              {[...assets]
                .sort((a, b) => a.symbol.localeCompare(b.symbol))
                .map((asset) => (
                  <SelectItem key={asset.id} value={asset.id}>
                    {asset.symbol}
                    {asset.exchange ? ` (${asset.exchange})` : ''}
                    {asset.name && asset.name !== asset.symbol ? ` - ${asset.name}` : ''}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
      )}
    </div>
  )
}
