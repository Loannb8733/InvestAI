import { useState } from 'react'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageSkeleton } from '@/components/ui/page-skeleton'
import QueryErrorState from '@/components/ui/query-error-state'
import DeleteNoteDialog from '@/features/journal/components/DeleteNoteDialog'
import NoteFilters from '@/features/journal/components/NoteFilters'
import NoteFormDialog from '@/features/journal/components/NoteFormDialog'
import NoteList from '@/features/journal/components/NoteList'
import NoteSummaryCards from '@/features/journal/components/NoteSummaryCards'
import ScorecardCard from '@/features/journal/components/ScorecardCard'
import { useNoteMutations, useNotes, useNoteSummary } from '@/features/journal/hooks'
import type { Note } from '@/features/journal/types'
import { useDebouncedValue } from '@/shared/lib/useDebouncedValue'

const TITLE = 'Journal'
const DESCRIPTION = 'Prenez des notes sur vos investissements et stratégies.'
const SEARCH_DELAY_MS = 300

export default function NotesPage() {
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Note | null>(null)
  const [deleting, setDeleting] = useState<Note | null>(null)
  const [search, setSearch] = useState('')
  const [selectedTag, setSelectedTag] = useState<string | null>(null)

  const notes = useNotes(useDebouncedValue(search, SEARCH_DELAY_MS), selectedTag)
  const { data: summary } = useNoteSummary()
  const closeDialog = () => {
    setCreating(false)
    setEditing(null)
  }
  const { create, update, remove } = useNoteMutations(closeDialog)

  if (notes.isLoading) {
    return <PageSkeleton titre={TITLE} description={DESCRIPTION} forme="liste" action />
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-serif font-medium">{TITLE}</h1>
          <p className="text-muted-foreground">{DESCRIPTION}</p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Nouvelle note
        </Button>
      </div>
      {summary && <NoteSummaryCards summary={summary} />}
      <ScorecardCard />
      <NoteFilters
        search={search}
        onSearch={setSearch}
        tags={summary?.unique_tags ?? []}
        selectedTag={selectedTag}
        onSelectTag={setSelectedTag}
      />
      {notes.isError ? (
        <QueryErrorState
          error={notes.error}
          onRetry={() => notes.refetch()}
          busy={notes.isFetching}
          title="Notes indisponibles"
          description="Le journal n'a pas pu être chargé."
        />
      ) : (
        <NoteList
          notes={notes.data?.pages.flat() ?? []}
          hasMore={notes.hasNextPage}
          loadingMore={notes.isFetchingNextPage}
          onMore={() => notes.fetchNextPage()}
          onCreate={() => setCreating(true)}
          onEdit={setEditing}
          onDelete={setDeleting}
        />
      )}
      <NoteFormDialog
        open={creating || editing !== null}
        note={editing}
        pending={create.isPending || update.isPending}
        onClose={closeDialog}
        onCreate={(body) => create.mutate(body)}
        onUpdate={(id, body) => update.mutate({ id, body })}
      />
      <DeleteNoteDialog
        note={deleting}
        onCancel={() => setDeleting(null)}
        onConfirm={(id) => {
          setDeleting(null)
          remove.mutate(id)
        }}
      />
    </div>
  )
}
