import { Shield } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { COLD_WALLETS } from '@/lib/platforms'

const WALLET_COLORS: Record<string, string> = {
  Tangem: 'bg-[oklch(var(--foreground))]',
  Ledger: 'bg-[oklch(var(--foreground))]',
  Trezor: 'bg-[oklch(var(--chart-3))]',
  SafePal: 'bg-[oklch(var(--chart-2))]',
  Metamask: 'bg-[#E2761B]',
}

const WALLET_LABELS: Record<string, string> = {
  Tangem: 'TG',
  Ledger: 'LG',
  Trezor: 'TZ',
  SafePal: 'SP',
  Metamask: 'MM',
}

export default function WalletsCard() {
  return (
    <Card elevation="raised">
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <Shield className="h-5 w-5 text-accent" />
          Mes wallets
        </CardTitle>
        <CardDescription>
          Portefeuilles matériels et wallets auto-custodial. Suivi manuel de vos actifs.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {COLD_WALLETS.map((wallet) => (
            <div key={wallet} className="flex items-center gap-3 p-4 rounded-lg border bg-muted/30">
              <div
                className={`${WALLET_COLORS[wallet] || 'bg-muted-foreground'} text-white rounded-xl flex items-center justify-center font-bold shrink-0`}
                style={{ width: 40, height: 40, fontSize: 14 }}
              >
                {WALLET_LABELS[wallet] || <Shield style={{ width: 20, height: 20 }} />}
              </div>
              <div className="flex-1">
                <h3 className="font-medium">{wallet}</h3>
                <p className="text-xs text-muted-foreground">Suivi manuel</p>
              </div>
              <Badge variant="outline" className="text-xs text-accent border-accent/30">
                <Shield className="h-3 w-3 mr-1" />
                Self-custody
              </Badge>
            </div>
          ))}
        </div>
        <p className="text-xs text-muted-foreground mt-4">
          Pour ajouter des actifs sur un wallet, allez dans votre portefeuille et enregistrez un transfert entrant avec la plateforme source.
        </p>
      </CardContent>
    </Card>
  )
}
