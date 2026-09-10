import { AlertTriangle, CheckCircle2, Clock } from 'lucide-react'
import type { CrowdfundingProject } from '@/types/crowdfunding'

/**
 * Les deux décisions d'affichage de la page « Mes Projets ».
 *
 * Sorties du composant pour être éprouvées directement : la page fait 1 073
 * lignes et était à 0 %, alors que ces deux fonctions gouvernent la pastille de
 * santé lue en premier sur chaque projet, et l'ordre dans lequel les six
 * projets réels apparaissent.
 *
 * (Un fichier à part, et non un export de plus depuis la page : ESLint refuse
 * qu'un module de composant exporte autre chose qu'un composant.)
 */

export type ScheduleHealth = 'none' | 'healthy' | 'warning' | 'danger'

/**
 * La pastille de santé d'un projet, lue depuis son échéancier.
 *
 * L'ordre des tests porte le sens : **un seul retard suffit** à faire passer le
 * projet au rouge, quel que soit le nombre d'échéances déjà honorées — c'est
 * l'information qui appelle une action. Sans retard, une échéance payée fait
 * foi que l'argent revient ; un échéancier entièrement à venir reste « en
 * attente », parce que rien n'a encore été prouvé.
 */
export function getScheduleHealth(project: CrowdfundingProject): ScheduleHealth {
  const schedule = project.schedule ?? []
  if (schedule.length === 0) return 'none'
  const overdueCount = schedule.filter((s) => s.status === 'overdue').length
  const paidCount = schedule.filter((s) => s.status === 'paid').length
  if (overdueCount > 0) return 'danger'
  if (paidCount > 0) return 'healthy'
  return 'warning'
}

export const HEALTH_CONFIG: Record<ScheduleHealth, { dot: string; label: string; icon: typeof CheckCircle2 }> = {
  none: { dot: 'bg-muted-foreground', label: 'Pas d\'échéancier', icon: Clock },
  healthy: { dot: 'bg-gain', label: 'À jour', icon: CheckCircle2 },
  warning: { dot: 'bg-warning', label: 'En attente', icon: Clock },
  danger: { dot: 'bg-loss', label: 'Retard détecté', icon: AlertTriangle },
}

/**
 * Filtre par statut puis ordonne, sans jamais toucher au tableau reçu.
 *
 * `sort` trie en place : appliqué directement aux données du cache de requêtes,
 * il réordonnerait la liste que d'autres vues partagent. La branche « tous »
 * recopie donc explicitement, là où `filter` produit déjà un nouveau tableau.
 */
export function trierEtFiltrer(
  projects: CrowdfundingProject[],
  statusFilter: string,
  sortBy: string,
): CrowdfundingProject[] {
  const list = statusFilter === 'all' ? [...projects] : projects.filter((p) => p.status === statusFilter)
  switch (sortBy) {
    case 'amount_desc': return list.sort((a, b) => Number(b.invested_amount) - Number(a.invested_amount))
    case 'amount_asc': return list.sort((a, b) => Number(a.invested_amount) - Number(b.invested_amount))
    case 'rate_desc': return list.sort((a, b) => Number(b.annual_rate) - Number(a.annual_rate))
    case 'rate_asc': return list.sort((a, b) => Number(a.annual_rate) - Number(b.annual_rate))
    case 'date_asc': return list.sort((a, b) => (a.start_date ?? '').localeCompare(b.start_date ?? ''))
    default: return list.sort((a, b) => (b.start_date ?? '').localeCompare(a.start_date ?? ''))
  }
}
