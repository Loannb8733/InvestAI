import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { ApiKey } from '../types'

interface RenameDialogProps {
  target: ApiKey | null
  exchangeName: (exchangeId: string) => string
  saving: boolean
  onSave: (id: string, label: string) => void
  onClose: () => void
}

type RenameFormProps = Omit<RenameDialogProps, 'target'> & { target: ApiKey }

function RenameForm({ target, exchangeName, saving, onSave, onClose }: RenameFormProps) {
  const [value, setValue] = useState(target.label || '')

  return (
    <>
      <DialogHeader>
        <DialogTitle>Renommer la connexion</DialogTitle>
        <DialogDescription>
          Modifiez le label de votre connexion{' '}
          <strong>{exchangeName(target.exchange)}</strong>.
        </DialogDescription>
      </DialogHeader>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          onSave(target.id, value.trim())
        }}
      >
        <div className="space-y-2 py-4">
          <Label htmlFor="rename-label">Label</Label>
          <Input
            id="rename-label"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder="Ex: Compte principal, DCA, Trading..."
            autoFocus
          />
          <p className="text-xs text-muted-foreground">Utile si vous avez plusieurs comptes sur le même exchange.</p>
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button type="submit" disabled={saving}>
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Enregistrer
          </Button>
        </DialogFooter>
      </form>
    </>
  )
}

export default function RenameDialog({ target, ...props }: RenameDialogProps) {
  return (
    <Dialog open={!!target} onOpenChange={(open) => !open && props.onClose()}>
      <DialogContent className="max-w-md">{target && <RenameForm key={target.id} target={target} {...props} />}</DialogContent>
    </Dialog>
  )
}
