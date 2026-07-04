import { cn } from "@/lib/utils"

/**
 * Squelettes de chargement.
 *
 * `Skeleton` : bloc de base (pulse + balayage lumineux GPU ; le balayage se
 * coupe seul sous `prefers-reduced-motion`, géré dans index.css).
 * `SkeletonText` / `SkeletonStatCard` : composés prêts à l'emploi pour
 * réserver l'espace exact du contenu (zéro layout shift au chargement).
 */

function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("skeleton-shimmer animate-pulse rounded-md bg-muted", className)}
      {...props}
    />
  )
}

/** Paragraphe fantôme — n lignes, la dernière raccourcie. */
function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={cn("space-y-2", className)} aria-hidden>
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton
          key={i}
          className={cn("h-3.5", i === lines - 1 ? "w-3/5" : "w-full")}
        />
      ))}
    </div>
  )
}

/** Fantôme d'une StatCard (label + grande valeur + sous-ligne). */
function SkeletonStatCard({ className }: { className?: string }) {
  return (
    <div
      className={cn("rounded-lg border border-border bg-card p-6 elev-1", className)}
      aria-hidden
    >
      <div className="flex items-center justify-between pb-3">
        <Skeleton className="h-3.5 w-24" />
        <Skeleton className="h-4 w-4 rounded-full" />
      </div>
      <Skeleton className="mb-2 h-8 w-36" />
      <Skeleton className="h-3 w-28" />
    </div>
  )
}

export { Skeleton, SkeletonText, SkeletonStatCard }
