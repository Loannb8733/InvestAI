import { useState } from 'react'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageSkeleton } from '@/components/ui/page-skeleton'
import NoteFilters from '@/features/journal/components/NoteFilters'
import NoteFormDialog from '@/features/journal/components/NoteFormDialog'
import NoteList from '@/features/journal/components/NoteList'
import NoteSummaryCards from '@/features/journal/components/NoteSummaryCards'
import ScorecardCard from '@/features/journal/components/ScorecardCard'
import { useAssetOptions, useNoteMutations, useNotes, useNoteSummary } from '@/features/journal/hooks'
import type { Note } from '@/features/journal/types'

const TITLE = 'Journal'
const DESCRIPTION = 'Prenez des notes sur vos investissements et stratégies.'

export default function NotesPage() {
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Note | null>(null)
  const [search, setSearch] = useState('')
  const [selectedTag, setSelectedTag] = useState<string | null>(null)
  const [page, setPage] = useState(0)

  const { data: notes, isLoading } = useNotes(search, selectedTag, page)
  const { data: summary } = useNoteSummary()
  const { data: assets } = useAssetOptions()
  const closeDialog = () => {
    setCreating(false)
    setEditing(null)
  }
  const { create, update, remove } = useNoteMutations(closeDialog)

  if (isLoading) {
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
      <NoteList
        notes={notes}
        page={page}
        onPage={setPage}
        onCreate={() => setCreating(true)}
        onEdit={setEditing}
        onDelete={(id) => remove.mutate(id)}
      />
      <NoteFormDialog
        open={creating || editing !== null}
        note={editing}
        assets={assets}
        pending={create.isPending || update.isPending}
        onClose={closeDialog}
        onCreate={(body) => create.mutate(body)}
        onUpdate={(id, body) => update.mutate({ id, body })}
      />
    </div>
  )
}
