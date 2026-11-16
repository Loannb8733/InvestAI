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
import { assetLabel, SENTIMENT_OPTIONS } from '../format'
import { useAssetOptions } from '../hooks'
import type { Note, NoteCreate, NoteUpdate } from '../types'

const NONE = 'none'

interface NoteFormDialogProps {
  open: boolean
  note: Note | null
  pending: boolean
  onClose: () => void
  onCreate: (body: NoteCreate) => void
  onUpdate: (id: string, body: NoteUpdate) => void
}

type NoteFormProps = Omit<NoteFormDialogProps, 'open'>

const chosen = (value: string) => (value === NONE ? null : value)

function NoteForm({ note, pending, onClose, onCreate, onUpdate }: NoteFormProps) {
  const { data: assets } = useAssetOptions()
  const [sentiment, setSentiment] = useState(note?.sentiment || NONE)
  const [linkedAssetId, setLinkedAssetId] = useState(note?.asset_id || NONE)

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const formData = new FormData(e.currentTarget)
    const text = (field: string) => (formData.get(field) as string) || null
    if (note) {
      onUpdate(note.id, {
        title: formData.get('title') as string,
        content: text('content'),
        tags: text('tags'),
        sentiment: chosen(sentiment),
        asset_id: chosen(linkedAssetId),
      })
    } else {
      onCreate({
        title: formData.get('title') as string,
        content: text('content') ?? undefined,
        tags: text('tags') ?? undefined,
        sentiment: chosen(sentiment) ?? undefined,
        asset_id: chosen(linkedAssetId) ?? undefined,
      })
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
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>Aucun sentiment</SelectItem>
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
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>Aucun actif</SelectItem>
              {assets?.map((asset) => (
                <SelectItem key={asset.id} value={asset.id}>
                  {assetLabel(asset)}
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
