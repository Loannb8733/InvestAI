import { FileText, Loader2, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import EmptyState from '@/components/ui/empty-state'
import type { Note } from '../types'
import NoteCard from './NoteCard'

interface NoteListProps {
  notes: Note[]
  hasMore: boolean
  loadingMore: boolean
  onMore: () => void
  onCreate: () => void
  onEdit: (note: Note) => void
  onDelete: (note: Note) => void
}

export default function NoteList({ notes, hasMore, loadingMore, onMore, onCreate, onEdit, onDelete }: NoteListProps) {
  if (notes.length === 0) {
    return (
      <EmptyState
        icon={FileText}
        title="Aucune note"
        description="Commencez à documenter vos décisions d'investissement."
        action={
          <Button onClick={onCreate}>
            <Plus className="h-4 w-4 mr-2" />
            Créer une note
          </Button>
        }
      />
    )
  }
  return (
    <>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {notes.map((note) => (
          <NoteCard key={note.id} note={note} onEdit={onEdit} onDelete={onDelete} />
        ))}
      </div>
      {hasMore && (
        <div className="flex justify-center mt-4">
          <Button variant="outline" onClick={onMore} disabled={loadingMore}>
            {loadingMore && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Charger plus
          </Button>
        </div>
      )}
    </>
  )
}
