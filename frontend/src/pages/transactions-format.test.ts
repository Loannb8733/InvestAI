import { describe, expect, it } from 'vitest'
import { formatQuantity, generateCSV, getDateRangeStart } from './transactions-format'

/**
 * Les trois fonctions pures de la page des transactions.
 *
 * `TransactionsPage` fait 1 497 lignes et n'était couverte à **0 %**. Monter la
 * page entière demanderait la moitié de l'application ; ces trois fonctions,
 * elles, portent des décisions qui se voient : comment une quantité s'affiche,
 * ce que « depuis le début de l'année » recouvre, et ce que contient le
 * fichier exporté.
 */

describe('affichage des quantités', () => {
  it('adapte la précision à la magnitude', () => {
    /* Une position de 12 000 jetons n'a pas besoin de six décimales, et
       0,00000123 BTC en a besoin de plus que deux. Quatre paliers, du millier
       au millionième. */
    // `toLocaleString('fr-FR')` sépare les milliers par une espace insécable
    // étroite (U+202F), non par une espace ordinaire — la comparaison de
    // chaînes s'y trompe facilement.
    expect(formatQuantity(12345.6789)).toBe('12\u202f345,68')
    expect(formatQuantity(12.3456789)).toBe('12,3457')
    expect(formatQuantity(0.12345678)).toBe('0,123457')
  })

  it('bascule en chiffres significatifs sous le dix-millième', () => {
    /* Sous ce seuil, un format à six décimales fixes rendrait « 0,000001 » —
       la valeur perd ses chiffres utiles. Quatre chiffres significatifs la
       préservent.

       L'assertion porte sur la valeur exacte : se contenter de « ce n'est pas
       zéro » laissait passer les deux formats, et le canari qui déplaçait le
       seuil restait muet. */
    expect(formatQuantity(0.00000123)).toBe('0,00000123')
  })

  it('rend « 0 » pour une quantité nulle ou illisible', () => {
    expect(formatQuantity(0)).toBe('0')
    expect(formatQuantity(NaN)).toBe('0')
  })

  it('conserve le signe des quantités négatives', () => {
    // Un ajustement de balance peut être négatif : le masquer ferait lire une
    // sortie comme une entrée.
    expect(formatQuantity(-5.5)).toMatch(/^-/)
  })

  it('sépare les milliers à la française', () => {
    expect(formatQuantity(1234567)).toBe('1\u202f234\u202f567')
  })
})

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
