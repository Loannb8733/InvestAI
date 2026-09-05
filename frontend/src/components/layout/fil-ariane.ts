import { createContext, useContext, useEffect } from 'react'
import { useLocation } from 'react-router-dom'

import { navGroups } from './navigation'

export interface EtapeFil {
  label: string
  path?: string
}

export interface ValeurContexte {
  surcharge: EtapeFil[] | null
  definir: (items: EtapeFil[] | null) => void
}

/**
 * Fil d'Ariane de l'application, affiché une seule fois — dans le Header.
 *
 * Cinq pages sur une vingtaine portaient leur propre fil, chacune à sa hauteur ;
 * les quinze autres n'avaient aucun repère, et l'espace gauche du Header restait
 * vide derrière un commentaire « Breadcrumb or page title could go here » jamais
 * honoré (UX-10).
 *
 * Le fil par défaut se dérive du rail : « [groupe] › [entrée] ». Rien à déclarer
 * pour une page ordinaire — elle est repérée dès qu'elle a une entrée de
 * navigation.
 *
 * Les pages à onglets appellent `useFilDAriane` pour suivre la section ouverte.
 * Le libellé de l'onglet reste défini dans la page, seule à le connaître : le
 * recopier dans `navigation.ts` créerait deux sources pour un même mot, donc
 * deux occasions de diverger.
 *
 * Le composant fournisseur vit dans `FilDArianeProvider.tsx` — un module qui
 * exporte à la fois un composant et des fonctions casse le rafraîchissement à
 * chaud.
 */
export const ContexteFil = createContext<ValeurContexte | null>(null)

/**
 * Déclare le fil de la page courante. À n'utiliser que lorsque le fil dérivé du
 * rail ne suffit pas — typiquement pour suivre l'onglet ouvert.
 */
export function useFilDAriane(items: EtapeFil[]) {
  const contexte = useContext(ContexteFil)
  // Le tableau est reconstruit à chaque rendu ; c'est son contenu qui doit
  // décider de la mise à jour, sans quoi l'effet se redéclenche sans fin.
  const empreinte = JSON.stringify(items)

  useEffect(() => {
    if (!contexte) return
    const definir = contexte.definir
    definir(JSON.parse(empreinte) as EtapeFil[])
    // Au départ de la page, le fil du rail reprend la main.
    return () => definir(null)
    // `definir` vient d'un `useState`, donc stable ; l'empreinte porte le contenu.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [empreinte])
}

/** « [groupe] › [entrée] » pour la route donnée, ou null si elle n'est pas au rail. */
export function filParDefaut(pathname: string): EtapeFil[] | null {
  let meilleur: { groupe: string; item: { label: string; path: string } } | null = null

  for (const groupe of navGroups) {
    for (const item of groupe.items) {
      const exact = item.path === pathname
      const sousRoute = item.path !== '/' && pathname.startsWith(item.path + '/')
      if (!exact && !sousRoute) continue
      // La correspondance la plus longue gagne : /crowdfunding/audit-lab doit
      // donner « Audit Lab », pas « Mes Projets ».
      if (!meilleur || item.path.length > meilleur.item.path.length) {
        meilleur = { groupe: groupe.label, item }
      }
    }
  }

  if (!meilleur) return null
  return [{ label: meilleur.groupe }, { label: meilleur.item.label }]
}

/** Fil à afficher : la surcharge de la page si elle existe, sinon celui du rail. */
export function useFilCourant(): EtapeFil[] | null {
  const contexte = useContext(ContexteFil)
  const { pathname } = useLocation()
  return contexte?.surcharge ?? filParDefaut(pathname)
}
