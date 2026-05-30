import { ResponsiveLine } from '@nivo/line'
import { oklchVar } from '@/lib/oklch'

interface SparklineProps {
  data: number[]
  positive: boolean
  width?: number
  height?: number
}

export function Sparkline({ data, positive, width = 80, height = 24 }: SparklineProps) {
  const color = positive ? oklchVar('--gain') : oklchVar('--loss')
  const chartData = [{ id: 'spark', data: data.map((v, i) => ({ x: i, y: v })) }]

  return (
    <div style={{ width, height }}>
      <ResponsiveLine
        data={chartData}
        margin={{ top: 2, right: 2, bottom: 2, left: 2 }}
        xScale={{ type: 'point' }}
        yScale={{ type: 'linear', min: 'auto', max: 'auto' }}
        curve="monotoneX"
        colors={[color]}
        lineWidth={1.5}
        enablePoints={false}
        enableGridX={false}
        enableGridY={false}
        axisTop={null}
        axisRight={null}
        axisBottom={null}
        axisLeft={null}
        enableSlices={false}
        isInteractive={false}
        animate={false}
      />
    </div>
  )
}
