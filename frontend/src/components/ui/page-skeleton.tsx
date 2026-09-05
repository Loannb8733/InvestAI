import { cn } from "@/lib/utils"
import { Skeleton } from "@/components/ui/skeleton"

/**
 * État de chargement d'une page entière.
 *
 * Remplace le `<Loader2>` centré que huit pages rendaient en retour anticipé.
 * Ce spinner posait trois problèmes mesurés :
 *
 * 1. **Il était muet.** Aucun des 95 `<Loader2>` du front ne portait de libellé
 *    accessible : pendant le chargement, un lecteur d'écran ne trouvait ni
 *    titre, ni contenu, ni annonce d'attente (WCAG 4.1.3, messages d'état).
 * 2. **Il emportait le titre.** Le retour anticipé remplaçait toute la page —
 *    sur Administration, Calendrier et Journal, dont le `<h1>` vit dans la page
 *    elle-même, il ne restait plus aucun titre de niveau 1.
 * 3. **Il ne disait rien de ce qui arrive.** Mesurée depuis la production, la
 *    latence d'un appel simple va de 0,48 à 0,95 s : le rond tourne environ une
 *    seconde sans annoncer si la page contiendra un tableau ou des cartes.
 *
 * Le niveau de titre est explicite, pas déduit : cinq des huit pages sont
 * montées sous un conteneur qui porte déjà le `<h1>` et n'utilisent qu'un
 * `<h2>` (UX-02). Un `<h1>` posé ici en dupliquerait un autre.
 */
interface PageSkeletonProps {
  /** Titre de la page — le même que celui du rendu chargé. */
  titre: string
  /** Sous-titre, quand la page en affiche un. */
  description?: string
  /**
   * Niveau du titre. `2` quand la page est montée sous un conteneur qui porte
   * déjà le `<h1>` de la route.
   */
  niveauTitre?: 1 | 2
  /** Forme du contenu attendu, pour que l'espace réservé lui ressemble. */
  forme?: "table" | "cartes" | "liste"
  /** Réserve la place d'un bouton d'action à droite du titre. */
  action?: boolean
  className?: string
}

function CorpsTable() {
  return (
    <div className="rounded-lg border border-border bg-card elev-1" aria-hidden>
      <div className="flex gap-4 border-b border-border px-4 py-3">
        {[28, 20, 16, 16, 12].map((w, i) => (
          <Skeleton key={i} className="h-3.5" style={{ width: `${w}%` }} />
        ))}
      </div>
      {Array.from({ length: 6 }, (_, r) => (
        <div key={r} className="flex gap-4 border-b border-border/50 px-4 py-4 last:border-0">
          {[28, 20, 16, 16, 12].map((w, i) => (
            <Skeleton key={i} className="h-4" style={{ width: `${w}%` }} />
          ))}
        </div>
      ))}
    </div>
  )
}

function CorpsCartes() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-hidden>
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} className="rounded-lg border border-border bg-card p-5 elev-1">
          <div className="mb-4 flex items-center justify-between">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-6 w-6 rounded-full" />
          </div>
          <Skeleton className="mb-2 h-7 w-28" />
          <Skeleton className="h-3 w-40" />
        </div>
      ))}
    </div>
  )
}

function CorpsListe() {
  return (
    <div className="space-y-3" aria-hidden>
      {Array.from({ length: 5 }, (_, i) => (
        <div key={i} className="flex items-start gap-4 rounded-lg border border-border bg-card p-4 elev-1">
          <Skeleton className="h-10 w-10 shrink-0 rounded-full" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-3 w-2/3" />
          </div>
        </div>
      ))}
    </div>
  )
}

export function PageSkeleton({
  titre,
  description,
  niveauTitre = 1,
  forme = "cartes",
  action = false,
  className,
}: PageSkeletonProps) {
  const Titre = niveauTitre === 1 ? "h1" : "h2"

  return (
    <div className={cn("space-y-6", className)} aria-busy="true">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-2">
          <Titre className="text-3xl font-serif font-medium">{titre}</Titre>
          {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
        </div>
        {action ? <Skeleton className="h-10 w-40 shrink-0" aria-hidden /> : null}
      </div>

      {/* L'annonce d'attente, que le spinner ne faisait pas. `polite` : elle ne
          coupe pas la lecture en cours, elle s'y ajoute. */}
      <p role="status" aria-live="polite" className="sr-only">
        Chargement de {titre} en cours…
      </p>

      {forme === "table" ? <CorpsTable /> : forme === "liste" ? <CorpsListe /> : <CorpsCartes />}
    </div>
  )
}
