import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useToast } from '@/hooks/use-toast'
import { notesApi } from '@/services/api'
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
} from 'lucide-react'

const SENTIMENT_OPTIONS = [
  { value: 'bullish', label: 'Bullish', icon: TrendingUp, color: 'text-green-500' },
  { value: 'bearish', label: 'Bearish', icon: TrendingDown, color: 'text-red-500' },
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

export default function NotesPage() {
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const [showAddNote, setShowAddNote] = useState(false)
  const [editingNote, setEditingNote] = useState<Note | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedTag, setSelectedTag] = useState<string | null>(null)

  // Fetch notes
  const { data: notes, isLoading } = useQuery<Note[]>({
    queryKey: ['notes', searchTerm, selectedTag],
    queryFn: () => notesApi.list({
      search: searchTerm || undefined,
      tag: selectedTag || undefined,
    }),
  })

  // Fetch summary
  const { data: summary } = useQuery<NoteSummary>({
    queryKey: ['notes-summary'],
    queryFn: notesApi.getSummary,
  })

  // Create note mutation
  const createMutation = useMutation({
    mutationFn: notesApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notes'] })
      queryClient.invalidateQueries({ queryKey: ['notes-summary'] })
      setShowAddNote(false)
      toast({ title: 'Note creee', description: 'La note a ete ajoutee avec succes.' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de creer la note.' })
    },
  })

  // Update note mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof notesApi.update>[1] }) =>
      notesApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notes'] })
      queryClient.invalidateQueries({ queryKey: ['notes-summary'] })
      setEditingNote(null)
      toast({ title: 'Note mise a jour' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de modifier la note.' })
    },
  })

  // Delete note mutation
  const deleteMutation = useMutation({
    mutationFn: notesApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notes'] })
      queryClient.invalidateQueries({ queryKey: ['notes-summary'] })
      toast({ title: 'Note supprimee' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de supprimer la note.' })
    },
  })

  const [sentiment, setSentiment] = useState<string>('')

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const formData = new FormData(e.currentTarget)

    const data = {
      title: formData.get('title') as string,
      content: formData.get('content') as string || undefined,
      tags: formData.get('tags') as string || undefined,
      sentiment: sentiment || undefined,
    }

    if (editingNote) {
      updateMutation.mutate({ id: editingNote.id, data })
    } else {
      createMutation.mutate(data)
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
          <h1 className="text-3xl font-bold">Journal</h1>
          <p className="text-muted-foreground">
            Prenez des notes sur vos investissements et strategies.
          </p>
        </div>
        <Button onClick={() => setShowAddNote(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Nouvelle note
        </Button>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Total notes
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{summary.total_notes}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Ce mois-ci
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{summary.notes_this_month}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Tags utilises
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{summary.unique_tags.length}</div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Search and Filter */}
      <Card>
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
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {notes.map((note) => (
            <Card key={note.id} className="hover:shadow-md transition-shadow">
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between">
                  <CardTitle className="text-lg line-clamp-1">{note.title}</CardTitle>
                  <div className="flex gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => { setEditingNote(note); setSentiment(note.sentiment || '') }}
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
      ) : (
        <Card>
          <CardContent className="py-12">
            <div className="text-center space-y-4">
              <FileText className="h-16 w-16 mx-auto text-muted-foreground" />
              <h2 className="text-xl font-semibold">Aucune note</h2>
              <p className="text-muted-foreground max-w-md mx-auto">
                Commencez a documenter vos decisions d'investissement.
              </p>
              <Button onClick={() => setShowAddNote(true)}>
                <Plus className="h-4 w-4 mr-2" />
                Creer une note
              </Button>
            </div>
          </CardContent>
        </Card>
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
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {editingNote ? 'Modifier la note' : 'Nouvelle note'}
            </DialogTitle>
            <DialogDescription>
              {editingNote
                ? 'Modifiez les informations de votre note.'
                : 'Ajoutez une nouvelle note a votre journal.'}
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
                  placeholder="Ecrivez votre note ici..."
                  rows={6}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="tags">Tags (separes par des virgules)</Label>
                <Input
                  id="tags"
                  name="tags"
                  defaultValue={editingNote?.tags || ''}
                  placeholder="strategie, analyse, crypto"
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
                {editingNote ? 'Enregistrer' : 'Creer'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
