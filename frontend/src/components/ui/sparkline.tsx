import { LineChart, Line, ResponsiveContainer } from 'recharts'

interface SparklineProps {
  data: number[]
  positive: boolean
  width?: number
  height?: number
}

export function Sparkline({ data, positive, width = 80, height = 24 }: SparklineProps) {
  const chartData = data.map((v, i) => ({ i, v }))
  const color = positive ? '#22c55e' : '#ef4444'

  return (
    <ResponsiveContainer width={width} height={height}>
      <LineChart data={chartData}>
        <Line
          type="monotone"
          dataKey="v"
          stroke={color}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
