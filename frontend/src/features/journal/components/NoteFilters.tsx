import { Search } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'

interface NoteFiltersProps {
  search: string
  onSearch: (search: string) => void
  tags: string[]
  selectedTag: string | null
  onSelectTag: (tag: string | null) => void
}

export default function NoteFilters({ search, onSearch, tags, selectedTag, onSelectTag }: NoteFiltersProps) {
  return (
    <Card elevation="raised">
      <CardContent className="pt-6">
        <div className="flex flex-col md:flex-row gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Rechercher dans les notes..."
              value={search}
              onChange={(e) => onSearch(e.target.value)}
              className="pl-10"
            />
          </div>
          {tags.length > 0 && (
            <div className="flex flex-wrap gap-2">
              <Badge
                variant={selectedTag === null ? 'default' : 'outline'}
                className="cursor-pointer"
                onClick={() => onSelectTag(null)}
              >
                Tous
              </Badge>
              {tags.map((tag) => (
                <Badge
                  key={tag}
                  variant={selectedTag === tag ? 'default' : 'outline'}
                  className="cursor-pointer"
                  onClick={() => onSelectTag(tag)}
                >
                  {tag}
                </Badge>
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
