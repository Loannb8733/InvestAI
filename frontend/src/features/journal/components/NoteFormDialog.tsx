import { useState, type FormEvent } from 'react'
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
import { Textarea } from '@/components/ui/textarea'
import { SENTIMENT_OPTIONS } from '../format'
import type { AssetOption, Note, NoteCreate, NoteUpdate } from '../types'

const NO_ASSET = 'none'

interface NoteFormDialogProps {
  open: boolean
  note: Note | null
  assets: AssetOption[] | undefined
  pending: boolean
  onClose: () => void
  onCreate: (body: NoteCreate) => void
  onUpdate: (id: string, body: NoteUpdate) => void
}

type NoteFormProps = Omit<NoteFormDialogProps, 'open'>

function NoteForm({ note, assets, pending, onClose, onCreate, onUpdate }: NoteFormProps) {
  const [sentiment, setSentiment] = useState(note?.sentiment || '')
  const [linkedAssetId, setLinkedAssetId] = useState(note?.asset_id || NO_ASSET)

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const formData = new FormData(e.currentTarget)
    const base = {
      title: formData.get('title') as string,
      content: (formData.get('content') as string) || undefined,
      tags: (formData.get('tags') as string) || undefined,
      sentiment: sentiment || undefined,
    }
    if (note) {
      onUpdate(note.id, { ...base, asset_id: linkedAssetId !== NO_ASSET ? linkedAssetId : null })
    } else {
      onCreate({ ...base, asset_id: linkedAssetId !== NO_ASSET ? linkedAssetId : undefined })
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="space-y-4 py-4">
        <div className="space-y-2">
          <Label htmlFor="title">Titre *</Label>
          <Input id="title" name="title" defaultValue={note?.title || ''} placeholder="Titre de la note" required />
        </div>
        <div className="space-y-2">
          <Label htmlFor="content">Contenu</Label>
          <Textarea
            id="content"
            name="content"
            defaultValue={note?.content || ''}
            placeholder="Écrivez votre note ici..."
            rows={6}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="tags">Tags (séparés par des virgules)</Label>
          <Input id="tags" name="tags" defaultValue={note?.tags || ''} placeholder="stratégie, analyse, crypto" />
        </div>
        <div className="space-y-2">
          <Label>Sentiment</Label>
          <Select value={sentiment} onValueChange={setSentiment}>
            <SelectTrigger>
              <SelectValue placeholder="Aucun sentiment" />
            </SelectTrigger>
            <SelectContent>
              {SENTIMENT_OPTIONS.map((s) => (
                <SelectItem key={s.value} value={s.value}>
                  <span className={`flex items-center gap-2 ${s.color}`}>
                    <s.icon className="h-4 w-4" />
                    {s.label}
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label>Actif lié (optionnel)</Label>
          <Select value={linkedAssetId} onValueChange={setLinkedAssetId}>
            <SelectTrigger>
              <SelectValue placeholder="Aucun actif" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NO_ASSET}>Aucun actif</SelectItem>
              {assets?.map((asset) => (
                <SelectItem key={asset.id} value={asset.id}>
                  {asset.symbol}
                  {asset.name ? ` — ${asset.name}` : ''}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose}>
          Annuler
        </Button>
        <Button type="submit" disabled={pending}>
          {pending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {note ? 'Enregistrer' : 'Créer'}
        </Button>
      </DialogFooter>
    </form>
  )
}

export default function NoteFormDialog({ open, ...form }: NoteFormDialogProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) form.onClose()
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{form.note ? 'Modifier la note' : 'Nouvelle note'}</DialogTitle>
          <DialogDescription>
            {form.note ? 'Modifiez les informations de votre note.' : 'Ajoutez une nouvelle note à votre journal.'}
          </DialogDescription>
        </DialogHeader>
        <NoteForm {...form} />
      </DialogContent>
    </Dialog>
  )
}
