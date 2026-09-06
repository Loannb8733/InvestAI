import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import { queryKeys } from './queryKeys'

/**
 * Toutes les clés de cache passent par `queryKeys`.
 *
 * Pourquoi ce garde-fou existe
 * ----------------------------
 * Sept requêtes déclaraient leur clé en toutes lettres. Deux composants
 * distincts — un badge et un camembert — répétaient `['platform-distribution']`
 * à l'identique, sans que rien ne signale leur parenté : renommer l'une aurait
 * silencieusement séparé deux caches qui doivent n'en faire qu'un.
 *
 * Aucun bug n'en découlait : TanStack invalide par préfixe, donc
 * `['dashboard', 0]` était bien purgé par `queryKeys.dashboard.all`. C'est la
 * cohérence qui manquait, pas la correction — et c'est précisément ce qu'un
 * test peut tenir dans la durée.
 */

const RACINE = join(__dirname, '..')

function fichiersSource(dossier: string): string[] {
  return readdirSync(dossier).flatMap((entree) => {
    const chemin = join(dossier, entree)
    if (statSync(chemin).isDirectory()) return fichiersSource(chemin)
    return /\.tsx?$/.test(entree) && !/\.test\.tsx?$/.test(entree) ? [chemin] : []
  })
}

describe('queryKeys — source unique des clés de cache', () => {
  it('aucune requête ne déclare sa clé en toutes lettres', () => {
    const fautifs: string[] = []

    for (const fichier of fichiersSource(RACINE)) {
      if (fichier.endsWith('queryKeys.ts')) continue
      const lignes = readFileSync(fichier, 'utf8').split('\n')

      lignes.forEach((ligne, i) => {
        if (!/queryKey:\s*\[/.test(ligne)) return
        // Une clé peut s'étendre sur plusieurs lignes : `queryKeys.` apparaît
        // alors juste en dessous. On regarde la ligne et les deux suivantes.
        const bloc = lignes.slice(i, i + 3).join(' ')
        if (!bloc.includes('queryKeys.')) {
          fautifs.push(`${fichier.replace(RACINE, 'src')}:${i + 1}`)
        }
      })
    }

    expect(fautifs, `clés en dur : ${fautifs.join(', ')}`).toEqual([])
  })

  it('les clés partagées sont bien uniques', () => {
    expect(queryKeys.platforms.distribution).toEqual(['platform-distribution'])
    expect(queryKeys.platforms.user).toEqual(['user-platforms'])
  })

  it("l'invalidation du dashboard couvre ses sous-clés", () => {
    expect(queryKeys.dashboard.munitions.slice(0, 1)).toEqual([...queryKeys.dashboard.all])
    expect(queryKeys.dashboard.metrics(0).slice(0, 1)).toEqual([...queryKeys.dashboard.all])
  })

  it("la projection d'objectif distingue ses paramètres", () => {
    expect(queryKeys.goals.projection('a', 100)).not.toEqual(queryKeys.goals.projection('a', 200))
    expect(queryKeys.goals.projection('a', 100)).not.toEqual(queryKeys.goals.projection('b', 100))
  })

  it('une projection sans montant omet le paramètre', () => {
    expect(queryKeys.goals.projection('a')).toEqual(['goals', 'projection', 'a'])
  })
})
