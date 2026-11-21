import { describe, expect, it } from 'vitest'
import { generateCSV, getDateRangeStart } from './format'

describe('plages de dates', () => {
  it('« tout » ne borne rien', () => {
    expect(getDateRangeStart('0')).toBeNull()
  })

  it("« depuis le 1er janvier » part du premier jour de l'année en cours", () => {
    const debut = getDateRangeStart('ytd')

    expect(debut?.getMonth()).toBe(0)
    expect(debut?.getDate()).toBe(1)
    expect(debut?.getFullYear()).toBe(new Date().getFullYear())
  })

  it('une plage en jours remonte au début de la journée', () => {
    /* Sans la remise à minuit, « 30 jours » couperait au milieu de la journée
       la plus ancienne et en masquerait une partie des mouvements. */
    const debut = getDateRangeStart('30')

    expect(debut?.getHours()).toBe(0)
    expect(debut?.getMinutes()).toBe(0)
  })

  it('une valeur illisible ne borne rien', () => {
    expect(getDateRangeStart('abc')).toBeNull()
  })
})

describe('export CSV', () => {
  const mouvement = {
    id: 't1',
    asset_symbol: 'BTC',
    transaction_type: 'buy',
    quantity: 0.5,
    price: 40000,
    fee: 12.5,
    executed_at: '2026-03-15T14:30:00Z',
    created_at: '2026-03-15T14:30:00Z',
    notes: 'achat DCA',
  } as unknown as Parameters<typeof generateCSV>[0][number]

  it('sépare les colonnes par un point-virgule et ouvre par un BOM', () => {
    const csv = generateCSV([mouvement])

    // Le BOM ouvre le fichier, donc la première ligne le porte.
    expect(csv.startsWith('\ufeff')).toBe(true)
    expect(csv.split('\n')[0]).toBe('\ufeffsymbol;type;quantity;price;fee;date;notes')
  })

  it('écrit les nombres avec un point décimal, pour le ré-import', () => {
    /* Contraste voulu avec l'export CSV du serveur, qui emploie la virgule
       depuis NEW-25 : celui-là s'ouvre dans Excel, celui-ci se réinjecte. Le
       parseur fait `Decimal(quantity_str)`, qui refuse la virgule —
       « harmoniser » les deux casserait le cycle export → ré-import. */
    const ligne = generateCSV([mouvement]).split('\n')[1]

    expect(ligne).toContain('0.5')
    expect(ligne).toContain('12.5')
    expect(ligne).not.toContain('0,5')
  })

  it('garde le type technique, que le serveur sait relire', () => {
    // « Achat » ne serait pas reconnu à l'import ; `buy` l'est.
    expect(generateCSV([mouvement]).split('\n')[1]).toContain('buy')
  })

  it('neutralise les points-virgules des notes', () => {
    // Une note contenant le séparateur décalerait toutes les colonnes
    // suivantes.
    const avecPointVirgule = { ...mouvement, notes: 'avant; après' }

    const ligne = generateCSV([avecPointVirgule]).split('\n')[1]

    expect(ligne.split(';')).toHaveLength(7)
    expect(ligne).toContain('avant, après')
  })

  it('aplatit les retours à la ligne des notes', () => {
    // Un saut de ligne créerait une ligne orpheline, illisible à l'import.
    const surDeuxLignes = { ...mouvement, notes: 'première\nseconde' }

    const csv = generateCSV([surDeuxLignes])

    expect(csv.split('\n')).toHaveLength(2) // en-tête + une ligne
  })

  it("retombe sur la date de création quand l'exécution manque", () => {
    const sansExecution = { ...mouvement, executed_at: null }

    expect(generateCSV([sansExecution]).split('\n')[1]).toContain('2026-03-15')
  })

  it('exporte un en-tête seul quand il n’y a rien à exporter', () => {
    expect(generateCSV([]).split('\n')).toHaveLength(1)
  })
})
