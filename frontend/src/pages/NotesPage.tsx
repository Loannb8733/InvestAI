import { useState } from 'react'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import StatCard from '@/components/ui/stat-card'
import SpotlightGroup from '@/components/ui/spotlight-group'
import EmptyState from '@/components/ui/empty-state'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { useToast } from '@/hooks/use-toast'
// Exception documentée : l'instance axios par défaut est importée directement
// car api.ts est maintenu par ailleurs (pas de notesApi.getScorecard à ce jour).
// Même pattern que CalendarPage pour /calendar/seed-tax-events.
import api, { notesApi, assetsApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Plus,
  Loader2,
  Trash2,
  Edit,
  Search,
  FileText,
  Tag,
  Calendar,
  TrendingUp,
  TrendingDown,
  Minus,
  Target,
  ChevronDown,
  ChevronUp,
  Check,
  X,
  Hourglass,
  AlertCircle,
} from 'lucide-react'

const SENTIMENT_OPTIONS = [
  { value: 'bullish', label: 'Bullish', icon: TrendingUp, color: 'text-gain' },
  { value: 'bearish', label: 'Bearish', icon: TrendingDown, color: 'text-loss' },
  { value: 'neutral', label: 'Neutre', icon: Minus, color: 'text-muted-foreground' },
]

interface Note {
  id: string
  title: string
  content: string | null
  tags: string | null
  asset_id: string | null
  asset_symbol: string | null
  asset_name: string | null
  transaction_ids: string | null
  attachments: string | null
  sentiment: string | null
  created_at: string
  updated_at: string
}

interface NoteSummary {
  total_notes: number
  notes_this_month: number
  unique_tags: string[]
}

interface AssetOption {
  id: string
  symbol: string
  name: string | null
}

type ScorecardVerdict = 'correct' | 'incorrect' | 'pending'

interface ScorecardEntry {
  note_id: string
  title: string
  symbol: string
  sentiment: string
  note_date: string
  perf_30d: number | null
  perf_90d: number | null
  verdict_30d: ScorecardVerdict
  verdict_90d: ScorecardVerdict
}

interface ScorecardSentimentStats {
  n: number
  hit_rate: number | null
}

interface ScorecardSummary {
  total_scored: number
  unscorable: number
  hit_rate_30d: number | null
  hit_rate_90d: number | null
  by_sentiment: Record<string, ScorecardSentimentStats>
}

interface ScorecardResponse {
  entries: ScorecardEntry[]
  summary: ScorecardSummary
}

/** Valeur sentinelle : les SelectItem de shadcn/ui n'acceptent pas la chaîne vide. */
const NO_ASSET = 'none'

const fmtCount = (n: number) => Math.round(n).toString()

const fmtHitRate = (v: number | null) => (v === null ? '—' : `${v.toFixed(0)} %`)

const fmtPerf = (v: number | null) => {
  if (v === null) return '—'
  return `${v > 0 ? '+' : ''}${v.toFixed(1)} %`
}

const perfClass = (v: number | null) => {
  if (v === null) return 'text-muted-foreground'
  if (v > 0) return 'text-gain'
  if (v < 0) return 'text-loss'
  return 'text-muted-foreground'
}

const VerdictIcon = ({ verdict }: { verdict: ScorecardVerdict }) => {
  if (verdict === 'correct') {
    return <Check className="h-4 w-4 text-gain" aria-label="Correct" />
  }
  if (verdict === 'incorrect') {
    return <X className="h-4 w-4 text-loss" aria-label="Incorrect" />
  }
  return <Hourglass className="h-4 w-4 text-muted-foreground" aria-label="En attente" />
}

export default function NotesPage() {
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const [showAddNote, setShowAddNote] = useState(false)
  const [editingNote, setEditingNote] = useState<Note | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedTag, setSelectedTag] = useState<string | null>(null)
  const [notesPage, setNotesPage] = useState(0)
  const NOTES_PER_PAGE = 50

  // Fetch notes
  const { data: notes, isLoading } = useQuery<Note[]>({
    queryKey: [...queryKeys.notes.list(searchTerm, selectedTag), notesPage],
    queryFn: () => notesApi.list({
      search: searchTerm || undefined,
      tag: selectedTag || undefined,
      skip: notesPage * NOTES_PER_PAGE,
      limit: NOTES_PER_PAGE,
    }),
    placeholderData: keepPreviousData,
  })

  // Fetch summary
  const { data: summary } = useQuery<NoteSummary>({
    queryKey: queryKeys.notes.summary,
    queryFn: notesApi.getSummary,
  })

  // Fetch assets for the "Actif lié" selector
  const { data: assets } = useQuery<AssetOption[]>({
    queryKey: queryKeys.assets.list(),
    queryFn: () => assetsApi.list(),
    staleTime: 60_000,
  })

  // Scorecard : chargée paresseusement au dépliage de la carte
  const [scorecardOpen, setScorecardOpen] = useState(false)
  const {
    data: scorecard,
    isLoading: scorecardLoading,
    isError: scorecardError,
  } = useQuery<ScorecardResponse>({
    queryKey: [...queryKeys.notes.all, 'scorecard'],
    // Appel direct via l'instance axios (voir commentaire d'import) plutôt
    // que via un wrapper notesApi, api.ts étant hors périmètre ici.
    queryFn: async (): Promise<ScorecardResponse> => {
      const response = await api.get('/notes/scorecard')
      return response.data
    },
    enabled: scorecardOpen,
    staleTime: 60_000,
  })

  // Create note mutation
  const createMutation = useMutation({
    mutationFn: notesApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.notes.all })
      queryClient.invalidateQueries({ queryKey: queryKeys.notes.summary })
      setShowAddNote(false)
      toast({ title: 'Note créée', description: 'La note a été ajoutée avec succès.' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de créer la note.' })
    },
  })

  // Update note mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof notesApi.update>[1] }) =>
      notesApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.notes.all })
      queryClient.invalidateQueries({ queryKey: queryKeys.notes.summary })
      setEditingNote(null)
      toast({ title: 'Note mise à jour' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de modifier la note.' })
    },
  })

  // Delete note mutation
  const deleteMutation = useMutation({
    mutationFn: notesApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.notes.all })
      queryClient.invalidateQueries({ queryKey: queryKeys.notes.summary })
      toast({ title: 'Note supprimée' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de supprimer la note.' })
    },
  })

  const [sentiment, setSentiment] = useState<string>('')
  const [linkedAssetId, setLinkedAssetId] = useState<string>(NO_ASSET)

  const openAddDialog = () => {
    setSentiment('')
    setLinkedAssetId(NO_ASSET)
    setShowAddNote(true)
  }

  const openEditDialog = (note: Note) => {
    setSentiment(note.sentiment || '')
    setLinkedAssetId(note.asset_id || NO_ASSET)
    setEditingNote(note)
  }

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const formData = new FormData(e.currentTarget)

    const base = {
      title: formData.get('title') as string,
      content: formData.get('content') as string || undefined,
      tags: formData.get('tags') as string || undefined,
      sentiment: sentiment || undefined,
    }

    if (editingNote) {
      // Édition : « Aucun actif » = DÉLIER explicitement (null) — le backend
      // distingue null (délier) d'absent (inchangé).
      updateMutation.mutate({
        id: editingNote.id,
        data: { ...base, asset_id: linkedAssetId !== NO_ASSET ? linkedAssetId : null },
      })
    } else {
      createMutation.mutate({
        ...base,
        asset_id: linkedAssetId !== NO_ASSET ? linkedAssetId : undefined,
      })
    }
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('fr-FR', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  const parseTags = (tags: string | null): string[] => {
    if (!tags) return []
    return tags.split(',').map(t => t.trim()).filter(Boolean)
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-serif font-medium">Journal</h1>
          <p className="text-muted-foreground">
            Prenez des notes sur vos investissements et stratégies.
          </p>
        </div>
        <Button onClick={openAddDialog}>
          <Plus className="h-4 w-4 mr-2" />
          Nouvelle note
        </Button>
      </div>

      {/* Summary Cards */}
      {summary && (
        <SpotlightGroup className="grid gap-4 md:grid-cols-3">
          <StatCard
            className="spot-card"
            label="Total notes"
            value={summary.total_notes}
            format={fmtCount}
          />
          <StatCard
            className="spot-card"
            label="Ce mois-ci"
            value={summary.notes_this_month}
            format={fmtCount}
          />
          <StatCard
            className="spot-card"
            label="Tags utilisés"
            value={summary.unique_tags.length}
            format={fmtCount}
          />
        </SpotlightGroup>
      )}

      {/* Scorecard : sentiment enregistré vs performance réalisée ensuite —
          la raison d'être d'un journal d'investissement. Chargée au dépliage. */}
      <Card elevation="raised">
        <CardHeader className="pb-2">
          <button
            type="button"
            className="flex w-full items-center justify-between text-left"
            onClick={() => setScorecardOpen((o) => !o)}
            aria-expanded={scorecardOpen}
          >
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Target className="h-4 w-4" aria-hidden />
              Scorecard de vos analyses
            </CardTitle>
            {scorecardOpen ? (
              <ChevronUp className="h-4 w-4 text-muted-foreground" aria-hidden />
            ) : (
              <ChevronDown className="h-4 w-4 text-muted-foreground" aria-hidden />
            )}
          </button>
        </CardHeader>
        {scorecardOpen && (
          <CardContent className="space-y-4">
            {scorecardLoading ? (
              <div className="space-y-2" aria-hidden>
                <Skeleton className="h-8 w-64" />
                <Skeleton className="h-24 w-full" />
              </div>
            ) : scorecardError ? (
              <p className="text-sm text-muted-foreground flex items-center gap-2">
                <AlertCircle className="h-4 w-4 text-loss" aria-hidden />
                Impossible de calculer la scorecard pour le moment.
              </p>
            ) : !scorecard || scorecard.summary.total_scored === 0 ? (
              <p className="text-sm text-muted-foreground">
                Liez des notes à des actifs avec un sentiment (Bullish/Bearish/Neutre) pour mesurer
                la qualité de vos analyses dans le temps.
                {scorecard && scorecard.summary.unscorable > 0 && (
                  <> {scorecard.summary.unscorable} note(s) liée(s) sans historique de prix exploitable.</>
                )}
              </p>
            ) : (
              <>
                <div className="flex flex-wrap items-baseline gap-x-8 gap-y-2">
                  <div>
                    <span className="text-xs text-muted-foreground">Taux de réussite à 30 j</span>
                    <p className="text-2xl font-serif font-medium tabular">
                      {fmtHitRate(scorecard.summary.hit_rate_30d)}
                    </p>
                  </div>
                  <div>
                    <span className="text-xs text-muted-foreground">à 90 j</span>
                    <p className="text-2xl font-serif font-medium tabular">
                      {fmtHitRate(scorecard.summary.hit_rate_90d)}
                    </p>
                  </div>
                  <div className="flex gap-4 text-xs text-muted-foreground">
                    {Object.entries(scorecard.summary.by_sentiment).map(([s, st]) => (
                      <span key={s} className="tabular">
                        {s === 'bullish' ? 'Bullish' : s === 'bearish' ? 'Bearish' : 'Neutre'} :{' '}
                        {fmtHitRate(st.hit_rate)} ({st.n})
                      </span>
                    ))}
                  </div>
                </div>
                {scorecard.summary.hit_rate_90d !== null && scorecard.summary.hit_rate_90d < 50 && (
                  <p className="text-xs text-warning">
                    Vos intuitions font moins bien que pile ou face sur 90 jours — le journal sert
                    exactement à voir ça.
                  </p>
                )}
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-xs text-muted-foreground">
                        <th scope="col" className="text-left p-2">Note</th>
                        <th scope="col" className="text-left p-2">Actif</th>
                        <th scope="col" className="text-left p-2">Sentiment</th>
                        <th scope="col" className="text-right p-2">Perf 30 j</th>
                        <th scope="col" className="text-center p-2">30 j</th>
                        <th scope="col" className="text-right p-2">Perf 90 j</th>
                        <th scope="col" className="text-center p-2">90 j</th>
                      </tr>
                    </thead>
                    <tbody>
                      {scorecard.entries.map((e) => (
                        <tr key={e.note_id} className="border-b last:border-b-0">
                          <td className="p-2 max-w-[220px]">
                            <span className="block truncate font-medium">{e.title}</span>
                            <span className="text-xs text-muted-foreground">
                              {new Date(e.note_date).toLocaleDateString('fr-FR')}
                            </span>
                          </td>
                          <td className="p-2 font-mono text-xs">{e.symbol}</td>
                          <td className="p-2">
                            <Badge variant="outline" className="text-xs">
                              {e.sentiment === 'bullish' ? 'Bullish' : e.sentiment === 'bearish' ? 'Bearish' : 'Neutre'}
                            </Badge>
                          </td>
                          <td className={`p-2 text-right tabular ${perfClass(e.perf_30d)}`}>{fmtPerf(e.perf_30d)}</td>
                          <td className="p-2 text-center"><VerdictIcon verdict={e.verdict_30d} /></td>
                          <td className={`p-2 text-right tabular ${perfClass(e.perf_90d)}`}>{fmtPerf(e.perf_90d)}</td>
                          <td className="p-2 text-center"><VerdictIcon verdict={e.verdict_90d} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  Verdict : Bullish correct si perf &gt; +2 %, Bearish correct si perf &lt; −2 %,
                  Neutre correct si |perf| ≤ 5 %.
                  {scorecard.summary.unscorable > 0 && (
                    <> {scorecard.summary.unscorable} note(s) non évaluable(s) (historique de prix manquant).</>
                  )}
                </p>
              </>
            )}
          </CardContent>
        )}
      </Card>

      {/* Search and Filter */}
      <Card elevation="raised">
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Rechercher dans les notes..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10"
              />
            </div>
            {summary && summary.unique_tags.length > 0 && (
              <div className="flex flex-wrap gap-2">
                <Badge
                  variant={selectedTag === null ? 'default' : 'outline'}
                  className="cursor-pointer"
                  onClick={() => setSelectedTag(null)}
                >
                  Tous
                </Badge>
                {summary.unique_tags.map((tag) => (
                  <Badge
                    key={tag}
                    variant={selectedTag === tag ? 'default' : 'outline'}
                    className="cursor-pointer"
                    onClick={() => setSelectedTag(tag)}
                  >
                    {tag}
                  </Badge>
                ))}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Notes List */}
      {notes && notes.length > 0 ? (
        <>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {notes.map((note) => (
            <Card key={note.id} elevation="raised">
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between">
                  <CardTitle className="text-lg line-clamp-1">{note.title}</CardTitle>
                  <div className="flex gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => openEditDialog(note)}
                      aria-label="Modifier la note"
                    >
                      <Edit className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => {
                        if (confirm('Supprimer cette note ?')) {
                          deleteMutation.mutate(note.id)
                        }
                      }}
                      aria-label="Supprimer la note"
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {note.content && (
                  <p className="text-sm text-muted-foreground line-clamp-3 mb-3">
                    {note.content}
                  </p>
                )}
                {note.tags && (
                  <div className="flex flex-wrap gap-1 mb-3">
                    {parseTags(note.tags).map((tag) => (
                      <Badge key={tag} variant="secondary" className="text-xs">
                        <Tag className="h-3 w-3 mr-1" />
                        {tag}
                      </Badge>
                    ))}
                  </div>
                )}
                <div className="flex flex-wrap gap-1 mb-2">
                  {note.asset_symbol && (
                    <Badge variant="outline" className="text-xs">
                      {note.asset_symbol}
                    </Badge>
                  )}
                  {note.sentiment && (() => {
                    const s = SENTIMENT_OPTIONS.find((o) => o.value === note.sentiment)
                    if (!s) return null
                    const Icon = s.icon
                    return (
                      <Badge variant="outline" className={`text-xs ${s.color}`}>
                        <Icon className="h-3 w-3 mr-1" />
                        {s.label}
                      </Badge>
                    )
                  })()}
                </div>
                <div className="flex items-center text-xs text-muted-foreground">
                  <Calendar className="h-3 w-3 mr-1" />
                  {formatDate(note.created_at)}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
        {notes && notes.length === NOTES_PER_PAGE && (
          <div className="flex justify-center mt-4">
            <Button variant="outline" onClick={() => setNotesPage((p) => p + 1)}>
              Charger plus
            </Button>
          </div>
        )}
        {notesPage > 0 && (
          <div className="flex justify-center mt-2">
            <Button variant="ghost" size="sm" onClick={() => setNotesPage(0)}>
              Retour au début
            </Button>
          </div>
        )}
        </>
      ) : (
        <EmptyState
          icon={FileText}
          title="Aucune note"
          description="Commencez à documenter vos décisions d'investissement."
          action={
            <Button onClick={openAddDialog}>
              <Plus className="h-4 w-4 mr-2" />
              Créer une note
            </Button>
          }
        />
      )}

      {/* Add/Edit Note Dialog */}
      <Dialog
        open={showAddNote || !!editingNote}
        onOpenChange={(open) => {
          if (!open) {
            setShowAddNote(false)
            setEditingNote(null)
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editingNote ? 'Modifier la note' : 'Nouvelle note'}
            </DialogTitle>
            <DialogDescription>
              {editingNote
                ? 'Modifiez les informations de votre note.'
                : 'Ajoutez une nouvelle note à votre journal.'}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSubmit}>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="title">Titre *</Label>
                <Input
                  id="title"
                  name="title"
                  defaultValue={editingNote?.title || ''}
                  placeholder="Titre de la note"
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="content">Contenu</Label>
                <Textarea
                  id="content"
                  name="content"
                  defaultValue={editingNote?.content || ''}
                  placeholder="Écrivez votre note ici..."
                  rows={6}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="tags">Tags (séparés par des virgules)</Label>
                <Input
                  id="tags"
                  name="tags"
                  defaultValue={editingNote?.tags || ''}
                  placeholder="stratégie, analyse, crypto"
                />
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
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setShowAddNote(false)
                  setEditingNote(null)
                }}
              >
                Annuler
              </Button>
              <Button
                type="submit"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                {(createMutation.isPending || updateMutation.isPending) && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                {editingNote ? 'Enregistrer' : 'Créer'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
