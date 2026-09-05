import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { ContexteFil, type EtapeFil } from './fil-ariane'

/** Fournit le fil d'Ariane au Header et aux pages. Voir `fil-ariane.ts`. */
export function FilDArianeProvider({ children }: { children: ReactNode }) {
  const [surcharge, definir] = useState<EtapeFil[] | null>(null)
  const valeur = useMemo(() => ({ surcharge, definir }), [surcharge])
  return <ContexteFil.Provider value={valeur}>{children}</ContexteFil.Provider>
}
