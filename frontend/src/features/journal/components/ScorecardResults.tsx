import { Check, Hourglass, X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { fmtHitRate, fmtPerf, perfClass, sentimentLabel } from '../format'
import type { Scorecard, ScorecardEntry } from '../types'

function VerdictIcon({ verdict }: { verdict: string }) {
  if (verdict === 'correct') {
    return <Check className="h-4 w-4 text-gain" aria-label="Correct" />
  }
  if (verdict === 'incorrect') {
    return <X className="h-4 w-4 text-loss" aria-label="Incorrect" />
  }
  return <Hourglass className="h-4 w-4 text-muted-foreground" aria-label="En attente" />
}

function EntryRow({ entry }: { entry: ScorecardEntry }) {
  return (
    <tr className="border-b last:border-b-0">
      <td className="p-2 max-w-[220px]">
        <span className="block truncate font-medium">{entry.title}</span>
        <span className="text-xs text-muted-foreground">{new Date(entry.note_date).toLocaleDateString('fr-FR')}</span>
      </td>
      <td className="p-2 font-mono text-xs">{entry.symbol}</td>
      <td className="p-2">
        <Badge variant="outline" className="text-xs">
          {sentimentLabel(entry.sentiment)}
        </Badge>
      </td>
      <td className={`p-2 text-right tabular ${perfClass(entry.perf_30d)}`}>{fmtPerf(entry.perf_30d)}</td>
      <td className="p-2 text-center"><VerdictIcon verdict={entry.verdict_30d} /></td>
      <td className={`p-2 text-right tabular ${perfClass(entry.perf_90d)}`}>{fmtPerf(entry.perf_90d)}</td>
      <td className="p-2 text-center"><VerdictIcon verdict={entry.verdict_90d} /></td>
    </tr>
  )
}

export default function ScorecardResults({ scorecard }: { scorecard: Scorecard }) {
  const { summary } = scorecard
  return (
    <>
      <div className="flex flex-wrap items-baseline gap-x-8 gap-y-2">
        <div>
          <span className="text-xs text-muted-foreground">Taux de réussite à 30 j</span>
          <p className="text-2xl font-serif font-medium tabular">{fmtHitRate(summary.hit_rate_30d)}</p>
        </div>
        <div>
          <span className="text-xs text-muted-foreground">à 90 j</span>
          <p className="text-2xl font-serif font-medium tabular">{fmtHitRate(summary.hit_rate_90d)}</p>
        </div>
        <div className="flex gap-4 text-xs text-muted-foreground">
          {Object.entries(summary.by_sentiment).map(([sentiment, stats]) => (
            <span key={sentiment} className="tabular">
              {sentimentLabel(sentiment)} :{' '}
              {fmtHitRate(stats.hit_rate)} ({stats.n})
            </span>
          ))}
        </div>
      </div>
      {summary.hit_rate_90d != null && summary.hit_rate_90d < 50 && (
        <p className="text-xs text-warning">
          Vos intuitions font moins bien que pile ou face sur 90 jours — le journal sert
          exactement à voir ça.
        </p>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-xs text-muted-foreground">
              <th scope="col" className="text-left p-2">Note</th>
              <th scope="col" className="text-left p-2">Actif</th>
              <th scope="col" className="text-left p-2">Sentiment</th>
              <th scope="col" className="text-right p-2">Perf 30 j</th>
              <th scope="col" className="text-center p-2">30 j</th>
              <th scope="col" className="text-right p-2">Perf 90 j</th>
              <th scope="col" className="text-center p-2">90 j</th>
            </tr>
          </thead>
          <tbody>
            {scorecard.entries.map((entry) => (
              <EntryRow key={entry.note_id} entry={entry} />
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-muted-foreground">
        Verdict : Bullish correct si perf &gt; +2 %, Bearish correct si perf &lt; −2 %,
        Neutre correct si |perf| ≤ 5 %.
        {summary.unscorable > 0 && (
          <> {summary.unscorable} note(s) non évaluable(s) (historique de prix manquant).</>
        )}
      </p>
    </>
  )
}
