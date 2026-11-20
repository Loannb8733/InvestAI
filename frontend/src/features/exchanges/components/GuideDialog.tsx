import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { guideFor } from '../guides/registry'
import type { Exchange } from '../types'
import ExchangeGuide from './ExchangeGuide'
import ExchangeLogo from './ExchangeLogo'

interface GuideDialogProps {
  exchangeId: string | null
  exchanges: Exchange[] | undefined
  onClose: () => void
  onConnect: (exchangeId: string) => void
}

function MissingGuide({ exchangeId, name, onClose }: { exchangeId: string; name?: string; onClose: () => void }) {
  return (
    <>
      <DialogHeader>
        <DialogTitle className="flex items-center gap-3">
          <ExchangeLogo exchange={exchangeId} size={32} />
          {name}
        </DialogTitle>
      </DialogHeader>
      <div className="py-4 text-sm text-muted-foreground">
        <p>Le guide pour cet exchange n'est pas encore disponible.</p>
        <p className="mt-2">En général, rendez-vous dans les paramètres de sécurité/API de votre exchange et créez une clé en <strong>lecture seule</strong>.</p>
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>
          Fermer
        </Button>
      </DialogFooter>
    </>
  )
}

export default function GuideDialog({ exchangeId, exchanges, onClose, onConnect }: GuideDialogProps) {
  const guide = exchangeId ? guideFor(exchangeId) : undefined

  return (
    <Dialog open={!!exchangeId} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        {exchangeId && guide && (
          <ExchangeGuide
            guide={guide}
            logo={<ExchangeLogo exchange={exchangeId} size={32} />}
            onClose={onClose}
            onConnect={() => onConnect(exchangeId)}
          />
        )}
        {exchangeId && !guide && (
          <MissingGuide
            exchangeId={exchangeId}
            name={exchanges?.find((exchange) => exchange.id === exchangeId)?.name}
            onClose={onClose}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}
