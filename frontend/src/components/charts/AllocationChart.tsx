import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts'
import { formatCurrency } from '@/lib/utils'

interface AllocationItem {
  type: string
  value: number
  percentage: number
}

interface AllocationChartProps {
  data: AllocationItem[]
}

const COLORS = {
  crypto: '#6366F1',
  stock: '#818CF8',
  etf: '#A78BFA',
  real_estate: '#F59E0B',
  bond: '#FBBF24',
  crowdfunding: '#10B981',
  other: '#64748B',
}

const LABELS = {
  crypto: 'Crypto',
  stock: 'Actions',
  etf: 'ETF',
  real_estate: 'Immobilier',
  bond: 'Obligations',
  crowdfunding: 'Crowdfunding',
  other: 'Autres',
}

export default function AllocationChart({ data }: AllocationChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="h-[300px] flex items-center justify-center text-muted-foreground">
        Aucune donnée disponible
      </div>
    )
  }

  const chartData = data.map((item) => ({
    name: LABELS[item.type as keyof typeof LABELS] || item.type,
    value: item.value,
    percentage: item.percentage,
    color: COLORS[item.type as keyof typeof COLORS] || COLORS.other,
  }))

  const CustomTooltip = ({ active, payload }: { active?: boolean; payload?: Array<{ payload: { name: string; value: number; percentage: number } }> }) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload
      return (
        <div className="bg-popover border rounded-lg shadow-lg p-3">
          <p className="font-medium">{data.name}</p>
          <p className="text-sm text-muted-foreground">
            {formatCurrency(data.value)}
          </p>
          <p className="text-sm text-muted-foreground">
            {data.percentage.toFixed(1)}%
          </p>
        </div>
      )
    }
    return null
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <PieChart>
        <defs>
          <filter id="pieGlow">
            <feGaussianBlur stdDeviation="2" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <Pie
          data={chartData}
          cx="50%"
          cy="50%"
          innerRadius={60}
          outerRadius={100}
          paddingAngle={2}
          dataKey="value"
          stroke="rgba(255,255,255,0.1)"
          strokeWidth={1}
        >
          {chartData.map((entry, index) => (
            <Cell key={`cell-${index}`} fill={entry.color} />
          ))}
        </Pie>
        <Tooltip content={<CustomTooltip />} />
        <Legend
          formatter={(value, entry) => {
            const percentage = (entry as { payload?: { percentage: number } }).payload?.percentage
            return (
              <span className="text-sm">
                {value} ({percentage?.toFixed(1)}%)
              </span>
            )
          }}
        />
      </PieChart>
    </ResponsiveContainer>
  )
}
