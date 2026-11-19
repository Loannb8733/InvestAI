import { Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { saveFile } from '../format'

const TEMPLATE =
  'symbol;type;quantity;price;fee;date;notes\nBTC;buy;0.5;45000;10;2024-01-15;Premier achat\nETH;buy;2;2500;5;2024-01-16;DCA mensuel'

const HINTS: Record<string, string> = {
  'Crypto.com': "Export depuis l'app (Paramètres → Exporter)",
  Binance: 'Historique des transactions',
  Kraken: 'Export des ledgers',
  'InvestAI / Generic': 'Format InvestAI (symbol, type, quantity, price, date)',
}

export default function SupportedPlatforms({ platforms }: { platforms: string[] }) {
  return (
    <div className="rounded-lg bg-muted p-4 text-sm">
      <p className="font-medium mb-2">Plateformes supportées :</p>
      <ul className="list-disc list-inside space-y-1 text-muted-foreground">
        {platforms.map((name) => (
          <li key={name}>
            <strong>{name}</strong>
            {HINTS[name] && ` - ${HINTS[name]}`}
          </li>
        ))}
      </ul>
      <p className="mt-3 text-muted-foreground">Les actifs sont créés automatiquement s'ils n'existent pas.</p>
      <Button
        variant="link"
        size="sm"
        className="mt-2 h-auto p-0"
        onClick={() => saveFile(new Blob([TEMPLATE], { type: 'text/csv;charset=utf-8;' }), 'template_transactions.csv')}
      >
        <Download className="h-3 w-3 mr-1" />
        Télécharger un modèle générique
      </Button>
    </div>
  )
}
