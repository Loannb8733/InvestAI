import { FileText, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import EmptyState from '@/components/ui/empty-state'
import { NOTES_PER_PAGE } from '../hooks'
import type { Note } from '../types'
import NoteCard from './NoteCard'

interface NoteListProps {
  notes: Note[] | undefined
  page: number
  onPage: (page: number) => void
  onCreate: () => void
  onEdit: (note: Note) => void
  onDelete: (id: string) => void
}

export default function NoteList({ notes, page, onPage, onCreate, onEdit, onDelete }: NoteListProps) {
  if (!notes || notes.length === 0) {
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
      {notes.length === NOTES_PER_PAGE && (
        <div className="flex justify-center mt-4">
          <Button variant="outline" onClick={() => onPage(page + 1)}>
            Charger plus
          </Button>
        </div>
      )}
      {page > 0 && (
        <div className="flex justify-center mt-2">
          <Button variant="ghost" size="sm" onClick={() => onPage(0)}>
            Retour au début
          </Button>
        </div>
      )}
    </>
  )
}
