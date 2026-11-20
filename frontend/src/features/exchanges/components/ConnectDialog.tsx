import type { FormEvent } from 'react'
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { ApiKeyCreate, Exchange } from '../types'
import ExchangeLogo from './ExchangeLogo'

interface ConnectDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  exchanges: Exchange[] | undefined
  selected: string
  onSelect: (exchangeId: string) => void
  pending: boolean
  onSubmit: (body: ApiKeyCreate) => void
}

function SecretField({ id, label, placeholder }: { id: string; label: string; placeholder: string }) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} name={id} type="password" placeholder={placeholder} />
    </div>
  )
}

export default function ConnectDialog({
  open,
  onOpenChange,
  exchanges,
  selected,
  onSelect,
  pending,
  onSubmit,
}: ConnectDialogProps) {
  const selectedInfo = exchanges?.find((exchange) => exchange.id === selected)

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    onSubmit({
      exchange: selected,
      label: (form.get('label') as string) || undefined,
      api_key: form.get('api_key') as string,
      secret_key: (form.get('secret_key') as string) || undefined,
      passphrase: (form.get('passphrase') as string) || undefined,
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Connecter un exchange</DialogTitle>
          <DialogDescription>
            Entrez vos clés API pour connecter votre exchange.
            Utilisez des clés en lecture seule pour plus de sécurité.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit}>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="exchange">Exchange</Label>
              <Select value={selected} onValueChange={onSelect}>
                <SelectTrigger>
                  <SelectValue placeholder="Sélectionner un exchange" />
                </SelectTrigger>
                <SelectContent>
                  {exchanges?.map((exchange) => (
                    <SelectItem key={exchange.id} value={exchange.id}>
                      <div className="flex items-center gap-2">
                        <ExchangeLogo exchange={exchange.id} size={20} />
                        <span>{exchange.name}</span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="label">Label (optionnel)</Label>
              <Input id="label" name="label" placeholder="Ex: Compte principal, DCA, Trading..." />
              <p className="text-xs text-muted-foreground">Utile si vous avez plusieurs comptes sur le même exchange.</p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="api_key">Clé API</Label>
              <Input id="api_key" name="api_key" type="password" placeholder="Votre clé API" required />
            </div>

            {selectedInfo?.requires_secret && (
              <SecretField id="secret_key" label="Clé secrète" placeholder="Votre clé secrète" />
            )}

            {selectedInfo?.requires_passphrase && (
              <SecretField id="passphrase" label="Passphrase" placeholder="Votre passphrase" />
            )}

            <div className="rounded-lg bg-warning/10 border border-warning/20 p-3 text-sm">
              <p className="text-warning dark:text-warning">
                <strong>Conseil sécurité:</strong> Créez des clés API en lecture seule
                sans permission de retrait pour protéger vos fonds.
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Annuler
            </Button>
            <Button type="submit" disabled={!selected || pending}>
              {pending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Connecter
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
