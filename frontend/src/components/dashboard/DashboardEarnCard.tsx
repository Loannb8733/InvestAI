import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { formatCurrency } from '@/lib/utils'
import { Lock, TrendingUp } from 'lucide-react'
import { AssetIconCompact } from '@/components/ui/asset-icon'

interface EarnAsset {
  symbol: string
  staked_quantity: number
  current_value: number
}

interface EarnSummary {
  total_staked_value: number
  total_rewards: number
  apr?: number
  assets: EarnAsset[]
}

export default function DashboardEarnCard({ earnSummary, privacyMode }: { earnSummary: EarnSummary; privacyMode?: boolean }) {
  const pc = (val: number) => privacyMode ? '••••••' : formatCurrency(val)

  return (
    <Card className="border-purple-500/20">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Lock className="h-4 w-4 text-purple-400" />
          Earn / Staking
          {earnSummary.apr != null && earnSummary.apr > 0 && (
            <Badge className="bg-green-500/10 text-green-500 border-green-500/30 text-[10px]">
              Yield {earnSummary.apr.toFixed(1)}%
            </Badge>
          )}
          <Badge className="ml-auto bg-purple-500/10 text-purple-400 border-purple-500/30 text-[10px]">
            {earnSummary.assets.length} actif{earnSummary.assets.length > 1 ? 's' : ''}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Total staked + rewards */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-muted-foreground">Valeur en Staking</p>
            <p className="text-2xl font-bold text-purple-400">{pc(earnSummary.total_staked_value)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              <TrendingUp className="h-3 w-3" />
              Rewards cumules
            </p>
            <p className={`text-lg font-bold ${earnSummary.total_rewards > 0 ? 'text-green-500' : 'text-muted-foreground'}`}>
              {earnSummary.total_rewards > 0 ? '+' : ''}{pc(earnSummary.total_rewards)}
            </p>
          </div>
        </div>

        {/* Asset breakdown */}
        <div className="border-t border-border pt-3 space-y-2">
          {earnSummary.assets.map((asset) => (
            <div key={asset.symbol} className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AssetIconCompact symbol={asset.symbol} name={asset.symbol} assetType="crypto" size={24} />
                <span className="text-sm font-medium">{asset.symbol}</span>
                <Badge className="bg-purple-500/10 text-purple-400 border-purple-500/30 text-[10px] px-1.5 py-0">
                  Staked
                </Badge>
              </div>
              <div className="text-right">
                <p className="text-sm font-medium">{pc(asset.current_value)}</p>
                <p className="text-[10px] text-muted-foreground">
                  {privacyMode ? '••••' : asset.staked_quantity.toFixed(asset.staked_quantity < 1 ? 6 : 2)} {asset.symbol}
                </p>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
