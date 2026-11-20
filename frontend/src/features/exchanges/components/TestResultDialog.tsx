import { CheckCircle, Wallet, XCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { counted, formatQuantity } from '@/lib/utils'
import type { TestResult } from '../types'

interface TestResultDialogProps {
  result: TestResult | null
  onClose: () => void
}

export default function TestResultDialog({ result, onClose }: TestResultDialogProps) {
  const balances = result?.balance ? Object.entries(result.balance) : []

  return (
    <Dialog open={!!result} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {result?.success ? <CheckCircle className="h-5 w-5 text-gain" /> : <XCircle className="h-5 w-5 text-loss" />}
            {result?.success ? 'Connexion réussie' : 'Échec de connexion'}
          </DialogTitle>
        </DialogHeader>
        <div className="py-4">
          <p className="text-muted-foreground">{result?.message}</p>
          {balances.length > 0 && (
            <div className="mt-4">
              <div className="flex items-center gap-2 mb-3">
                <Wallet className="h-4 w-4 text-muted-foreground" />
                <p className="font-medium">Soldes détectés ({counted(balances.length, 'actif', 'actifs')})</p>
              </div>
              <div className="grid gap-2 max-h-64 overflow-y-auto pr-2">
                {balances
                  .sort((a, b) => b[1] - a[1])
                  .map(([symbol, amount]) => (
                    <div key={symbol} className="flex justify-between items-center bg-muted p-2 rounded-md">
                      <span className="font-medium">{symbol}</span>
                      <span className="font-mono text-sm">{formatQuantity(amount)}</span>
                    </div>
                  ))}
              </div>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button onClick={onClose}>Fermer</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
