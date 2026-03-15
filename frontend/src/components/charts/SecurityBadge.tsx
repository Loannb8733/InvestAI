import { memo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { analyticsApi } from '@/services/api'
import { getTrustColor, getTrustLabel, getTrustScore } from '@/lib/platforms'
import { Shield, Loader2 } from 'lucide-react'

export default memo(function SecurityBadge() {
  const { data, isLoading } = useQuery({
    queryKey: ['platform-distribution'],
    queryFn: () => analyticsApi.getPlatformDistribution(),
    staleTime: 60_000,
  })

  if (isLoading) {
    return <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
  }

  if (!data || data.length === 0) return null

  // Weighted average trust score (weighted by value)
  const totalValue = data.reduce((sum, d) => sum + d.value, 0)
  if (totalValue === 0) return null

  const weightedScore = data.reduce((sum, d) => {
    const score = d.trust_score ?? getTrustScore(d.name)
    return sum + score * (d.value / totalValue)
  }, 0)

  const avgScore = Math.round(weightedScore * 10) / 10
  const color = getTrustColor(avgScore)
  const label = getTrustLabel(avgScore)

  return (
    <div className="flex items-center gap-2 rounded-lg border px-3 py-2" style={{ borderColor: color + '40' }}>
      <Shield className="h-5 w-5" style={{ color }} />
      <div>
        <p className="text-xs text-muted-foreground">Score de résilience</p>
        <p className="text-sm font-semibold" style={{ color }}>
          {avgScore.toFixed(1)}/10 — {label}
        </p>
      </div>
    </div>
  )
})
