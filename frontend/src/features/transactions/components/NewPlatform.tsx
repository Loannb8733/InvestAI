import { useState } from 'react'
import { Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const MAX_LENGTH = 50

interface NewPlatformProps {
  taken: (name: string) => boolean
  onCreate: (name: string) => void
  onCancel: () => void
}

export default function NewPlatform({ taken, onCreate, onCancel }: NewPlatformProps) {
  const [name, setName] = useState('')
  const trimmed = name.trim()
  const canCreate = trimmed.length > 0 && trimmed.length <= MAX_LENGTH && !taken(trimmed)
  const create = () => {
    if (canCreate) onCreate(trimmed)
  }

  return (
    <div className="space-y-2 rounded-lg border p-3">
      <div className="flex items-center justify-between">
        <Label className="text-xs font-medium">Nouvelle plateforme</Label>
        <Button type="button" variant="ghost" size="sm" className="h-auto py-0 px-1 text-xs" onClick={onCancel}>
          <X className="h-3 w-3" />
        </Button>
      </div>
      <div className="flex gap-2">
        <Input
          placeholder="Nom de la plateforme..."
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={MAX_LENGTH}
          autoFocus
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              create()
            }
          }}
        />
        <Button type="button" size="sm" disabled={!canCreate} onClick={create}>
          <Plus className="h-3 w-3 mr-1" />
          Ajouter
        </Button>
      </div>
      {trimmed.length > 0 && !canCreate && trimmed.length <= MAX_LENGTH && (
        <p className="text-xs text-muted-foreground">Cette plateforme existe déjà</p>
      )}
      {trimmed.length > MAX_LENGTH && <p className="text-xs text-destructive">50 caractères max</p>}
    </div>
  )
}
