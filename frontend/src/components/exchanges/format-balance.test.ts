import { describe, expect, it } from 'vitest'

import { formatBalance } from './format-balance'

/**
 * Un solde crypto va de la poussière au million. Un format unique ne convient
 * pas : quatre décimales noieraient une poussière dans des zéros, six sur un
 * solde à six chiffres seraient illisibles. La précision suit la grandeur, et
 * ce sont ces seuils que ces tests figent.
 */
describe('formatBalance', () => {
  it('rend un zéro net, sans décimale', () => {
    expect(formatBalance(0)).toBe('0')
  })

  it("bascule en notation scientifique sous 10⁻⁵", () => {
    // Six décimales afficheraient « 0.000001 » pour toute poussière : illisible
    // et faussement précis.
    expect(formatBalance(0.0000012)).toBe('1.20e-6')
  })

  it('donne six décimales sous l\'unité', () => {
    expect(formatBalance(0.5)).toBe('0.500000')
  })

  it('donne quatre décimales sous mille', () => {
    expect(formatBalance(12.3456789)).toBe('12.3457')
  })

  it('passe au séparateur de milliers au-delà', () => {
    const rendu = formatBalance(1234567.891)
    expect(rendu).toMatch(/1.234.567,89/)
  })

  it('ne perd pas la valeur juste sous un seuil', () => {
    expect(formatBalance(999.9999)).toBe('999.9999')
    expect(formatBalance(0.99999)).toBe('0.999990')
  })
})
