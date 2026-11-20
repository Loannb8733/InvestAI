import { describe, expect, it } from 'vitest'
import { counted, formatQuantity } from './utils'

describe('affichage des quantités', () => {
  it('adapte la précision à la magnitude', () => {
    expect(formatQuantity(12345.6789)).toBe('12 345,68')
    expect(formatQuantity(12.3456789)).toBe('12,3457')
    expect(formatQuantity(0.12345678)).toBe('0,123457')
  })

  it('bascule en chiffres significatifs sous le dix-millième', () => {
    expect(formatQuantity(0.00000123)).toBe('0,00000123')
  })

  it('rend « 0 » pour une quantité nulle ou illisible', () => {
    expect(formatQuantity(0)).toBe('0')
    expect(formatQuantity(NaN)).toBe('0')
  })

  it('conserve le signe des quantités négatives', () => {
    expect(formatQuantity(-5.5)).toMatch(/^-/)
  })

  it('sépare les milliers à la française', () => {
    expect(formatQuantity(1234567)).toBe('1 234 567')
  })
})

describe('accords', () => {
  it('garde le singulier pour zéro et un, le pluriel au-delà', () => {
    expect(counted(0, 'actif', 'actifs')).toBe('0 actif')
    expect(counted(1, 'actif', 'actifs')).toBe('1 actif')
    expect(counted(1500, 'actif', 'actifs')).toBe('1 500 actifs')
  })
})
