import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import SharedEmptyState from '@/components/ui/empty-state'
import { DollarSign } from 'lucide-react'

/** Skeleton commun aux sections de l'onglet Optimisations. */
export function Loader() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-5 w-48" />
        <Skeleton className="h-4 w-72 mt-1" />
      </CardHeader>
      <CardContent className="space-y-3">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-4/6" />
        <div className="flex gap-3 mt-4">
          <Skeleton className="h-10 w-24" />
          <Skeleton className="h-10 w-24" />
          <Skeleton className="h-10 w-24" />
        </div>
      </CardContent>
    </Card>
  )
}

/** État vide : composant partagé du design system, icône financière conservée. */
export function SectionEmptyState({ message }: { message: string }) {
  return <SharedEmptyState icon={DollarSign} title={message} />
}
