import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useMfaCode } from '../hooks'
import type { MfaSetup } from '../types'

interface MfaDialogProps {
  open: boolean
  enabled: boolean
  setup: MfaSetup | null
  onOpenChange: (open: boolean) => void
}

export default function MfaDialog({ open, enabled, setup, onOpenChange }: MfaDialogProps) {
  const [code, setCode] = useState('')
  const done = () => {
    onOpenChange(false)
    setCode('')
  }
  const verify = useMfaCode('verify', done)
  const disable = useMfaCode('disable', done)
  const pending = verify.isPending || disable.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{enabled ? 'Désactiver la MFA' : 'Configurer la MFA'}</DialogTitle>
          <DialogDescription>
            {enabled
              ? 'Entrez votre code MFA pour désactiver la double authentification.'
              : "Scannez le QR code avec votre application d'authentification (Google Authenticator, Authy, etc.)"}
          </DialogDescription>
        </DialogHeader>
        {!enabled && setup?.qr_code && (
          <div className="flex flex-col items-center space-y-4">
            <img src={setup.qr_code} alt="QR Code MFA" className="w-48 h-48" />
            <div className="text-center">
              <p className="text-sm text-muted-foreground mb-1">Clé secrète (si vous ne pouvez pas scanner) :</p>
              <code className="text-xs bg-muted px-2 py-1 rounded font-mono break-all">{setup.secret}</code>
            </div>
          </div>
        )}
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="mfaCode">Code à 6 chiffres</Label>
            <Input
              id="mfaCode"
              placeholder="000000"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            />
          </div>
          <Button
            className="w-full"
            onClick={() => (enabled ? disable.mutate(code) : verify.mutate(code))}
            disabled={code.length !== 6 || pending}
          >
            {pending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            {enabled ? 'Désactiver la MFA' : 'Vérifier et activer'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
