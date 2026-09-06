import { CheckCircle, Wallet, XCircle } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { TestResult } from '@/types/exchanges'

import { formatBalance } from './format-balance'

/**
 * Résultat d'un test de connexion à une plateforme.
 *
 * Extrait d'`ExchangesPage`, où il vivait parmi quatre autres dialogues au
 * fond d'une fonction de 1 334 lignes. Il ne dépend que du résultat à
 * afficher : `null` le ferme, ce qui laisse à la page la maîtrise de son
 * ouverture.
 */
interface TestResultDialogProps {
  resultat: TestResult | null
  onFermer: () => void
}

export default function TestResultDialog({ resultat, onFermer }: TestResultDialogProps) {
  const soldes = resultat?.balance ? Object.entries(resultat.balance) : []

  return (
    <Dialog open={!!resultat} onOpenChange={onFermer}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {resultat?.success ? (
              <CheckCircle className="h-5 w-5 text-gain" />
            ) : (
              <XCircle className="h-5 w-5 text-loss" />
            )}
            {resultat?.success ? 'Connexion réussie' : 'Échec de connexion'}
          </DialogTitle>
        </DialogHeader>
        <div className="py-4">
          <p className="text-muted-foreground">{resultat?.message}</p>
          {soldes.length > 0 && (
            <div className="mt-4">
              <div className="flex items-center gap-2 mb-3">
                <Wallet className="h-4 w-4 text-muted-foreground" />
                <p className="font-medium">Soldes détectés ({soldes.length} actifs)</p>
              </div>
              <div className="grid gap-2 max-h-64 overflow-y-auto pr-2">
                {soldes
                  .sort((a, b) => b[1] - a[1])
                  .map(([symbol, amount]) => (
                    <div
                      key={symbol}
                      className="flex justify-between items-center bg-muted p-2 rounded-md"
                    >
                      <span className="font-medium">{symbol}</span>
                      <span className="font-mono text-sm">{formatBalance(amount)}</span>
                    </div>
                  ))}
              </div>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button onClick={onFermer}>Fermer</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
