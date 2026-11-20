import { AlertCircle, CheckCircle, Coins, Info, Loader2, RefreshCw, Scale } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { counted, formatCurrency, formatDateTime } from '@/lib/utils'
import { totalMissingEur } from '../format'
import type { Reconciliation } from '../reconciliation'
import GapTable from './GapTable'

export default function ReconciliationCard({ reconciliation }: { reconciliation: Reconciliation }) {
  const { check, verify, credit } = reconciliation

  return (
    <Card elevation="raised">
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <Scale className="h-5 w-5 text-accent" />
          Réconciliation
        </CardTitle>
        <CardDescription>
          Compare les soldes rapportés par vos exchanges avec vos transactions importées pour
          détecter les récompenses non tracées (intérêts Earn, airdrops, vouchers...).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <Button
            variant="outline"
            onClick={() => verify.mutate()}
            disabled={verify.isPending}
            className="w-full sm:w-auto gap-2"
          >
            {verify.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Vérifier les écarts
          </Button>
          {check && (
            <span className="text-xs text-muted-foreground">
              Dernière vérification : {formatDateTime(check.checkedAt.toISOString())}
            </span>
          )}
        </div>

        {!check && (
          <p className="text-sm text-muted-foreground">
            Cliquez sur « Vérifier les écarts » pour lancer une comparaison. Une vérification
            est aussi effectuée automatiquement après chaque import d'historique.
          </p>
        )}

        {check && check.gaps.length === 0 && (
          <div className="flex items-center gap-2 text-sm text-gain bg-gain/10 p-3 rounded-md">
            <CheckCircle className="h-4 w-4 shrink-0" />
            <span>Aucun écart détecté ✓</span>
          </div>
        )}

        {check && check.gaps.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-start gap-2 text-sm text-warning bg-warning/10 p-3 rounded-md">
              <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
              <span>
                {counted(check.gaps.length, 'récompense non tracée détectée', 'récompenses non tracées détectées')}
                {' — total estimé '}
                {formatCurrency(totalMissingEur(check.gaps))}.
              </span>
            </div>
            <GapTable gaps={check.gaps} />
            <Button onClick={() => credit.mutate()} disabled={credit.isPending} className="gap-2">
              {credit.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Coins className="h-4 w-4" />}
              Créditer en airdrop
            </Button>
          </div>
        )}

        <p className="text-xs text-muted-foreground flex items-start gap-1.5">
          <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
          <span>
            Le crédit auto valorise au prix du jour — pour des revenus perçus antérieurement,
            la base fiscale exacte est le prix au jour de perception.
          </span>
        </p>
      </CardContent>
    </Card>
  )
}
