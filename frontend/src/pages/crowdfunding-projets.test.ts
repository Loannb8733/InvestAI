import { describe, expect, it } from 'vitest'
import type { CrowdfundingProject } from '@/types/crowdfunding'
import { HEALTH_CONFIG, getScheduleHealth, trierEtFiltrer } from './crowdfunding-projets'

/**
 * Les deux décisions d'affichage de « Mes Projets ».
 *
 * La page fait 1 073 lignes et était à **0 %**, alors qu'elle montre les six
 * projets de crowdfunding réels. Ces deux fonctions en sont le cœur : l'une
 * décide la pastille de couleur lue en premier sur chaque carte, l'autre
 * l'ordre dans lequel les projets apparaissent.
 */

function projet(surcharge: Partial<CrowdfundingProject> = {}): CrowdfundingProject {
  return {
    id: 'p1',
    platform: 'Lymo',
    project_name: 'Résidence',
    invested_amount: 1000,
    annual_rate: 9,
    duration_months: 24,
    repayment_type: 'in_fine',
    status: 'active',
    ...surcharge,
  } as CrowdfundingProject
}

const echeance = (status: string) => ({ status }) as CrowdfundingProject['schedule'][number]

describe('la pastille de santé', () => {
  it('reste neutre quand aucun échéancier n’a été généré', () => {
    expect(getScheduleHealth(projet({ schedule: [] }))).toBe('none')
    expect(getScheduleHealth(projet())).toBe('none')
  })

  it('passe au rouge dès un seul retard', () => {
    // Un retard appelle une action ; le nombre d'échéances déjà honorées ne
    // l'annule pas. C'est l'ordre des tests dans la fonction qui le garantit.
    const projetAvecRetard = projet({
      schedule: [echeance('paid'), echeance('paid'), echeance('paid'), echeance('overdue')],
    })

    expect(getScheduleHealth(projetAvecRetard)).toBe('danger')
  })

  it('est au vert dès qu’une échéance a été honorée', () => {
    expect(getScheduleHealth(projet({ schedule: [echeance('paid'), echeance('pending')] }))).toBe('healthy')
  })

  it('reste en attente tant que rien n’a été versé ni manqué', () => {
    // Un échéancier entièrement à venir n'a rien prouvé : ni bon payeur, ni
    // mauvais. L'orange dit exactement cela.
    expect(getScheduleHealth(projet({ schedule: [echeance('pending'), echeance('pending')] }))).toBe('warning')
  })

  it('donne un libellé et une couleur à chacun des quatre états', () => {
    // La pastille est lue à la couleur ; le libellé la rend accessible à qui ne
    // la distingue pas.
    for (const etat of ['none', 'healthy', 'warning', 'danger'] as const) {
      expect(HEALTH_CONFIG[etat].label).toBeTruthy()
      expect(HEALTH_CONFIG[etat].dot).toMatch(/^bg-/)
    }
    expect(HEALTH_CONFIG.danger.label).toMatch(/[Rr]etard/)
  })
})

describe('le filtrage et le tri', () => {
  const actifs = [
    projet({ id: 'a', status: 'active', invested_amount: 500, annual_rate: 12, start_date: '2026-01-01' }),
    projet({ id: 'b', status: 'active', invested_amount: 3000, annual_rate: 7, start_date: '2026-06-01' }),
    projet({ id: 'c', status: 'completed', invested_amount: 1500, annual_rate: 9, start_date: '2025-03-01' }),
  ]

  const ids = (liste: CrowdfundingProject[]) => liste.map((p) => p.id)

  it('ne touche jamais au tableau reçu', () => {
    // `sort` trie en place : appliqué aux données du cache de requêtes, il
    // réordonnerait la liste que les autres vues partagent.
    const original = [...actifs]

    trierEtFiltrer(actifs, 'all', 'amount_desc')

    expect(ids(actifs)).toEqual(ids(original))
  })

  it('garde tous les projets quand aucun statut n’est demandé', () => {
    expect(trierEtFiltrer(actifs, 'all', 'date_desc')).toHaveLength(3)
  })

  it('ne garde que le statut demandé', () => {
    expect(ids(trierEtFiltrer(actifs, 'completed', 'date_desc'))).toEqual(['c'])
  })

  it('ordonne du plus gros au plus petit montant', () => {
    expect(ids(trierEtFiltrer(actifs, 'all', 'amount_desc'))).toEqual(['b', 'c', 'a'])
  })

  it('ordonne du plus petit au plus gros montant', () => {
    expect(ids(trierEtFiltrer(actifs, 'all', 'amount_asc'))).toEqual(['a', 'c', 'b'])
  })

  it('ordonne par taux décroissant puis croissant', () => {
    expect(ids(trierEtFiltrer(actifs, 'all', 'rate_desc'))).toEqual(['a', 'c', 'b'])
    expect(ids(trierEtFiltrer(actifs, 'all', 'rate_asc'))).toEqual(['b', 'c', 'a'])
  })

  it('ordonne par date de début, du plus récent par défaut', () => {
    expect(ids(trierEtFiltrer(actifs, 'all', 'date_desc'))).toEqual(['b', 'a', 'c'])
    expect(ids(trierEtFiltrer(actifs, 'all', 'date_asc'))).toEqual(['c', 'a', 'b'])
  })

  it('retombe sur la date décroissante devant un tri inconnu', () => {
    expect(ids(trierEtFiltrer(actifs, 'all', 'tri-inexistant'))).toEqual(['b', 'a', 'c'])
  })

  it('place un projet sans date de début en dernier', () => {
    // Une chaîne vide se compare avant toute date : en ordre décroissant, elle
    // finit donc la liste plutôt que de la commencer.
    const sansDate = projet({ id: 'd', status: 'active', start_date: undefined })

    expect(ids(trierEtFiltrer([...actifs, sansDate], 'all', 'date_desc')).at(-1)).toBe('d')
  })

  it('compare les montants comme des nombres, non comme du texte', () => {
    // Les montants arrivent parfois en chaînes depuis l'API : un tri textuel
    // placerait « 900 » après « 1000 ».
    const a = projet({ id: 'petit', invested_amount: '900' as unknown as number })
    const b = projet({ id: 'gros', invested_amount: '1000' as unknown as number })

    expect(ids(trierEtFiltrer([a, b], 'all', 'amount_desc'))).toEqual(['gros', 'petit'])
  })
})
