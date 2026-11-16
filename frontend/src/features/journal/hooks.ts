import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useToast } from '@/hooks/use-toast'
import { queryKeys } from '@/lib/queryKeys'
import { apiClient } from '@/shared/api/client'
import type { NoteCreate, NoteUpdate } from './types'

export const NOTES_PER_PAGE = 50

export function useNotes(search: string, tag: string | null) {
  return useInfiniteQuery({
    queryKey: queryKeys.notes.list(search, tag),
    queryFn: ({ pageParam }) =>
      apiClient.get('/notes', {
        query: {
          search: search || undefined,
          tag: tag || undefined,
          skip: pageParam * NOTES_PER_PAGE,
          limit: NOTES_PER_PAGE,
        },
        silent: true,
      }),
    initialPageParam: 0,
    getNextPageParam: (lastPage, pages) => (lastPage.length === NOTES_PER_PAGE ? pages.length : undefined),
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
    queryFn: () => apiClient.get('/notes/scorecard', { silent: true }),
    staleTime: 60_000,
  })
}

export function useNoteMutations(onSaved: () => void) {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.notes.all })

  const create = useMutation({
    mutationFn: (body: NoteCreate) => apiClient.post('/notes', { body, silent: true }),
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
      apiClient.patch('/notes/{note_id}', { path: { note_id: id }, body, silent: true }),
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
    mutationFn: (id: string) => apiClient.delete('/notes/{note_id}', { path: { note_id: id }, silent: true }),
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
