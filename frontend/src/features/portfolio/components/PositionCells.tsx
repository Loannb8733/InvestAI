import { Sparkline } from '@/components/ui/sparkline'
import { riskClass } from '../format'
import type { SparklineSeries } from '../types'

export function RiskCell({ weight, className }: { weight: number; className: string }) {
  return (
    <td className={`text-center ${className} hidden lg:table-cell`}>
      {weight > 0 ? (
        <span className={`text-xs px-2 py-0.5 rounded ${riskClass(weight)}`}>{weight.toFixed(1)}%</span>
      ) : (
        '-'
      )}
    </td>
  )
}

export function SparkCell({ series, className }: { series: SparklineSeries | undefined; className: string }) {
  return (
    <td className={`text-center ${className} hidden lg:table-cell`}>
      {series ? (
        <div className="flex justify-center">
          <Sparkline data={series.prices} positive={series.change_pct >= 0} />
        </div>
      ) : (
        <span className="text-xs text-muted-foreground">-</span>
      )}
    </td>
  )
}
