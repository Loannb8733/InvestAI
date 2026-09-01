import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { formatCurrency } from './utils'

/**
 * ARC-11 — un seul point de formatage des montants.
 *
 * Pourquoi c'est une règle et pas un détail
 * -----------------------------------------
 * `CalendarPage` affichait « 1 234 EUR » quand le reste de l'app affichait
 * « 1 234,00 € » : deux écrans, deux rendus, pour la même donnée. Le formatage
 * dispersé dérive toujours — sur le séparateur, le nombre de décimales, la
 * position du symbole — parce que rien ne force les copies à évoluer ensemble.
 *
 * Le garde-fou statique compte autant que les tests de comportement : c'est lui
 * qui empêche le prochain `Intl.NumberFormat` local de réapparaître.
 */

describe('formatCurrency', () => {
  it('formate un montant en euros à la française', () => {
    // Intl utilise l'espace insécable étroit (U+202F) comme séparateur de
    // milliers en fr-FR : on normalise plutôt que de coder l'octet en dur.
    expect(formatCurrency(1234.5).replace(/\s/g, ' ')).toBe('1 234,50 €')
  })

  it('honore la devise passée en second argument', () => {
    expect(formatCurrency(1234.5, 'USD')).toContain('$')
  })

  it('accepte une chaîne — les montants arrivent souvent en string de l\'API', () => {
    expect(formatCurrency('1234.5')).toBe(formatCurrency(1234.5))
  })

  it('rend un tiret pour une valeur absente ou non numérique', () => {
    expect(formatCurrency(null)).toBe('—')
    expect(formatCurrency(undefined)).toBe('—')
    expect(formatCurrency('abc')).toBe('—')
    expect(formatCurrency(Number.NaN)).toBe('—')
    expect(formatCurrency(Number.POSITIVE_INFINITY)).toBe('—')
  })

  it('arrondit sans lever quand on demande zéro décimale', () => {
    // minimumFractionDigits (2 par défaut) > maximumFractionDigits lèverait un
    // RangeError : le minimum doit suivre le maximum vers le bas.
    expect(() => formatCurrency(1234.56, 'EUR', { maximumFractionDigits: 0 })).not.toThrow()
    expect(formatCurrency(1234.56, 'EUR', { maximumFractionDigits: 0 })).not.toContain(',')
  })

  it('garde deux décimales par défaut', () => {
    expect(formatCurrency(1234)).toContain(',00')
  })

  it('formate zéro comme un montant, pas comme une valeur absente', () => {
    // `value == null` ne doit pas attraper 0 : un solde nul est une information.
    expect(formatCurrency(0)).not.toBe('—')
  })
})

/** Tous les fichiers source, hors tests et hors l'util lui-même. */
function fichiersSource(dir: string, acc: string[] = []): string[] {
  for (const entree of readdirSync(dir)) {
    const chemin = join(dir, entree)
    if (statSync(chemin).isDirectory()) {
      fichiersSource(chemin, acc)
    } else if (/\.tsx?$/.test(entree) && !/\.test\.tsx?$/.test(entree)) {
      acc.push(chemin)
    }
  }
  return acc
}

describe('aucun formatage monétaire hors de lib/utils', () => {
  const racine = resolve(process.cwd(), 'src')
  const util = resolve(racine, 'lib/utils.ts')

  it('aucun Intl.NumberFormat en style currency ailleurs', () => {
    const coupables = fichiersSource(racine)
      .filter((f) => resolve(f) !== util)
      .filter((f) => /style:\s*['"]currency['"]/.test(readFileSync(f, 'utf-8')))

    expect(coupables, 'formatage monétaire local : utiliser formatCurrency').toEqual([])
  })

  it('aucun montant assemblé à la main avec EUR ou €', () => {
    const coupables = fichiersSource(racine)
      .filter((f) => resolve(f) !== util)
      .filter((f) => {
        const src = readFileSync(f, 'utf-8')
        // « <nombre>.toLocaleString(...) EUR » ou « ... € » sur la même ligne.
        return src
          .split('\n')
          .some((l) => /toLocaleString\(/.test(l) && /(\bEUR\b|€)/.test(l))
      })

    expect(coupables, 'montant concaténé à un symbole : utiliser formatCurrency').toEqual([])
  })
})
