import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { formatCurrency } from '@/lib/utils'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import { LineChart as LineChartIcon } from 'lucide-react'

interface ChartDataPoint {
  date: string
  fullDate: string
  value: number
  invested: number
  gain: number
}

interface PortfolioEvolutionChartProps {
  chartHistoricalData: ChartDataPoint[]
}

const chartTooltipStyle: React.CSSProperties = {
  backgroundColor: 'hsl(var(--popover))',
  borderColor: 'hsl(var(--border))',
  color: 'hsl(var(--popover-foreground))',
  borderRadius: '0.5rem',
  fontSize: 12,
}

const axisTick = { fill: 'hsl(var(--muted-foreground))', fontSize: 12 }

export default function PortfolioEvolutionChart({ chartHistoricalData }: PortfolioEvolutionChartProps) {
  if (chartHistoricalData.length === 0) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <LineChartIcon className="h-5 w-5" />
          Évolution du portefeuille
        </CardTitle>
        <CardDescription>Valeur totale vs montant investi</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartHistoricalData}>
              <defs>
                <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                </linearGradient>
                <linearGradient id="colorInvested" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#94a3b8" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#94a3b8" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis dataKey="date" tick={axisTick} interval="preserveStartEnd" />
              <YAxis tickFormatter={(v) => formatCurrency(v).replace('\u20AC', '')} tick={axisTick} width={80} />
              <RechartsTooltip
                contentStyle={chartTooltipStyle}
                formatter={(value: number, name: string) => [
                  formatCurrency(value),
                  name === 'value' ? 'Valeur' : 'Investi'
                ]}
              />
              <Legend formatter={(value) => value === 'value' ? 'Valeur actuelle' : 'Montant investi'} />
              <Area type="monotone" dataKey="invested" stroke="#94a3b8" strokeWidth={2} fillOpacity={1} fill="url(#colorInvested)" />
              <Area type="monotone" dataKey="value" stroke="#3b82f6" strokeWidth={2} fillOpacity={1} fill="url(#colorValue)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  )
}
