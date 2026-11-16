import { useState } from 'react'
import { AlertCircle, ChevronDown, ChevronUp, Target } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useScorecard } from '../hooks'
import ScorecardResults from './ScorecardResults'

function ScorecardBody() {
  const { data: scorecard, isLoading, isError } = useScorecard()
  if (isLoading) {
    return (
      <div className="space-y-2" aria-hidden>
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-24 w-full" />
      </div>
    )
  }
  if (isError) {
    return (
      <p className="text-sm text-muted-foreground flex items-center gap-2">
        <AlertCircle className="h-4 w-4 text-loss" aria-hidden />
        Impossible de calculer la scorecard pour le moment.
      </p>
    )
  }
  if (!scorecard || scorecard.summary.total_scored === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Liez des notes à des actifs avec un sentiment (Bullish/Bearish/Neutre) pour mesurer
        la qualité de vos analyses dans le temps.
        {scorecard && scorecard.summary.unscorable > 0 && (
          <> {scorecard.summary.unscorable} note(s) liée(s) sans historique de prix exploitable.</>
        )}
      </p>
    )
  }
  return <ScorecardResults scorecard={scorecard} />
}

export default function ScorecardCard() {
  const [open, setOpen] = useState(false)
  return (
    <Card elevation="raised">
      <CardHeader className="pb-2">
        <button
          type="button"
          className="flex w-full items-center justify-between text-left"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
        >
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Target className="h-4 w-4" aria-hidden />
            Scorecard de vos analyses
          </CardTitle>
          {open ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground" aria-hidden />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground" aria-hidden />
          )}
        </button>
      </CardHeader>
      {open && (
        <CardContent className="space-y-4">
          <ScorecardBody />
        </CardContent>
      )}
    </Card>
  )
}
