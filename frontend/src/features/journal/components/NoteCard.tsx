import { Calendar, Edit, Tag, Trash2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatNoteDate, parseTags, SENTIMENT_OPTIONS } from '../format'
import type { Note } from '../types'

interface NoteCardProps {
  note: Note
  onEdit: (note: Note) => void
  onDelete: (id: string) => void
}

function SentimentBadge({ sentiment }: { sentiment: string }) {
  const option = SENTIMENT_OPTIONS.find((o) => o.value === sentiment)
  if (!option) return null
  const Icon = option.icon
  return (
    <Badge variant="outline" className={`text-xs ${option.color}`}>
      <Icon className="h-3 w-3 mr-1" />
      {option.label}
    </Badge>
  )
}

export default function NoteCard({ note, onEdit, onDelete }: NoteCardProps) {
  return (
    <Card elevation="raised">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <CardTitle className="text-lg line-clamp-1">{note.title}</CardTitle>
          <div className="flex gap-1">
            <Button variant="ghost" size="icon" onClick={() => onEdit(note)} aria-label="Modifier la note">
              <Edit className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => {
                if (confirm('Supprimer cette note ?')) {
                  onDelete(note.id)
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
        {note.content && <p className="text-sm text-muted-foreground line-clamp-3 mb-3">{note.content}</p>}
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
          {note.sentiment && <SentimentBadge sentiment={note.sentiment} />}
        </div>
        <div className="flex items-center text-xs text-muted-foreground">
          <Calendar className="h-3 w-3 mr-1" />
          {formatNoteDate(note.created_at)}
        </div>
      </CardContent>
    </Card>
  )
}
