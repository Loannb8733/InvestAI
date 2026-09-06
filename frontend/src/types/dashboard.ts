/**
 * Types partagés par les deux tableaux de bord.
 *
 * `/` (vue globale) et `/crypto` (vue crypto) consomment le **même** endpoint,
 * `dashboardApi.getMetrics`, mais déclaraient chacune ses types. Quatre
 * d'entre eux portaient le même nom des deux côtés — deux à l'identique, deux
 * en divergeant.
 *
 * La divergence n'était pas anodine : la vue globale déclarait
 * `roi_annualized: number` là où l'API renvoie `None` dès que la période est
 * trop courte pour annualiser un rendement. Le code s'en protégeait par un
 * `?? null`, donc rien ne cassait ; mais le type invitait à écrire
 * `roi_annualized.toFixed(2)`, qui aurait planté en production sur un compte
 * neuf.
 *
 * `DashboardMetrics` reste déclaré dans chaque page : les deux vues lisent le
 * même endpoint mais n'en exploitent pas les mêmes champs — 20 d'un côté, 35
 * de l'autre. Les fondre imposerait à chacune de connaître ce dont elle n'a
 * pas l'usage.
 */

/** Alerte de prix active, telle que le dashboard la reçoit. */
export interface ActiveAlert {
  id: string
  name: string
  symbol?: string
  condition: string
  threshold: number
  current_price?: number
}

/** Échéance à venir : dividende, loyer, remboursement. */
export interface UpcomingEvent {
  id: string
  title: string
  event_type: string
  event_date: string
  amount?: number
}
