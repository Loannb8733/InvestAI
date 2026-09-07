import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * Deux librairies de graphiques, une frontière (ADR-010).
 *
 * Pourquoi ce garde-fou existe
 * ----------------------------
 * Le ticket d'audit demandait de « retirer la librairie non utilisée ». Les
 * deux servent : Nivo dans 24 fichiers, Lightweight Charts dans un seul
 * composant — la série temporelle navigable du dashboard, que Nivo ne sait
 * pas rendre (crosshair sur l'axe temps, pan, zoom).
 *
 * Le vrai coût n'était pas la cohabitation mais le chunk : `manualChunks`
 * rangeait les deux sous le même nom, si bien que la moindre page à
 * camembert téléchargeait aussi les 169 kB de Lightweight Charts — et que le
 * `lazy()` posé sur `PortfolioAreaChart` ne protégeait plus rien.
 *
 * Ces deux tests tiennent la décision dans la durée : la frontière d'usage,
 * et la séparation des chunks qui la rend mesurable.
 */

const RACINE = join(__dirname, '..', '..')

/** Les seuls fichiers autorisés à importer Lightweight Charts. */
const PORTEE_SERIE_TEMPORELLE = [
  'components/charts/PortfolioAreaChart.tsx',
  'components/charts/lightweight-theme.ts',
]

function fichiersSource(dossier: string): string[] {
  return readdirSync(dossier).flatMap((entree) => {
    const chemin = join(dossier, entree)
    if (statSync(chemin).isDirectory()) return fichiersSource(chemin)
    return /\.tsx?$/.test(entree) && !/\.test\.tsx?$/.test(entree) ? [chemin] : []
  })
}

describe('stratégie des librairies de graphiques', () => {
  it("Lightweight Charts ne sort pas du composant de série temporelle", () => {
    const horsPerimetre: string[] = []

    for (const fichier of fichiersSource(RACINE)) {
      const relatif = fichier.slice(RACINE.length + 1).replace(/\\/g, '/')
      if (PORTEE_SERIE_TEMPORELLE.includes(relatif)) continue
      if (!/from '[^']*lightweight-charts'/.test(readFileSync(fichier, 'utf8'))) continue
      horsPerimetre.push(relatif)
    }

    expect(
      horsPerimetre,
      `Lightweight Charts importé hors de sa portée (${horsPerimetre.join(', ')}). ` +
        "Voir docs/ADR.md ADR-010 : les graphiques analytiques passent par Nivo.",
    ).toEqual([])
  })

  it('les deux librairies restent dans des chunks distincts', () => {
    const config = readFileSync(join(RACINE, '..', 'vite.config.ts'), 'utf8')
    const chunks = [...config.matchAll(/return '(charts-[a-z]+)'/g)].map((m) => m[1])

    expect(new Set(chunks).size, `chunks de graphiques déclarés : ${chunks.join(', ')}`).toBe(2)
    expect(config).toMatch(/@nivo\|d3-\)\/\.test\(id\)\) return 'charts-nivo'/)
    expect(config).toMatch(/lightweight-charts\/\.test\(id\)\) return 'charts-timeseries'/)
  })
})
