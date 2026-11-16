import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useToast } from '@/hooks/use-toast'
import { queryKeys } from '@/lib/queryKeys'
import { apiClient } from '@/shared/api/client'
import type { NoteCreate, NoteUpdate } from './types'

export const NOTES_PER_PAGE = 50

export function useNotes(search: string, tag: string | null, page: number) {
  return useQuery({
    queryKey: [...queryKeys.notes.list(search, tag), page],
    queryFn: () =>
      apiClient.get('/notes', {
        query: {
          search: search || undefined,
          tag: tag || undefined,
          skip: page * NOTES_PER_PAGE,
          limit: NOTES_PER_PAGE,
        },
      }),
    placeholderData: keepPreviousData,
  })
}

export function useNoteSummary() {
  return useQuery({ queryKey: queryKeys.notes.summary, queryFn: () => apiClient.get('/notes/summary') })
}

export function useAssetOptions() {
  return useQuery({ queryKey: queryKeys.assets.list(), queryFn: () => apiClient.get('/assets'), staleTime: 60_000 })
}

export function useScorecard() {
  return useQuery({
    queryKey: [...queryKeys.notes.all, 'scorecard'],
    queryFn: () => apiClient.get('/notes/scorecard'),
    staleTime: 60_000,
  })
}

export function useNoteMutations(onSaved: () => void) {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.notes.all })
    queryClient.invalidateQueries({ queryKey: queryKeys.notes.summary })
  }

  const create = useMutation({
    mutationFn: (body: NoteCreate) => apiClient.post('/notes', { body }),
    onSuccess: () => {
      refresh()
      onSaved()
      toast({ title: 'Note créée', description: 'La note a été ajoutée avec succès.' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de créer la note.' })
    },
  })

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: NoteUpdate }) =>
      apiClient.patch('/notes/{note_id}', { path: { note_id: id }, body }),
    onSuccess: () => {
      refresh()
      onSaved()
      toast({ title: 'Note mise à jour' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de modifier la note.' })
    },
  })

  const remove = useMutation({
    mutationFn: (id: string) => apiClient.delete('/notes/{note_id}', { path: { note_id: id } }),
    onSuccess: () => {
      refresh()
      toast({ title: 'Note supprimée' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de supprimer la note.' })
    },
  })

  return { create, update, remove }
}
