/**
 * Taux d'inflation suggérés par devise.
 *
 * Le sélecteur qui les propose est écrit **deux fois** dans la page — une fois
 * dans l'onglet FIRE, une fois dans Projection — à l'identique. Extraire la
 * table est le premier pas ; fondre les deux sélecteurs en un composant reste
 * à faire, et demande d'abord un test qui couvre le changement de devise.
 */
export const INFLATION_BY_CURRENCY: Record<string, { rate: number; label: string }> = {
  EUR: { rate: 2.0, label: '2.0% (zone euro)' },
  USD: { rate: 2.5, label: '2.5% (US)' },
  GBP: { rate: 2.0, label: '2.0% (UK)' },
  CHF: { rate: 0.5, label: '0.5% (Suisse)' },
  JPY: { rate: 1.0, label: '1.0% (Japon)' },
  CAD: { rate: 2.0, label: '2.0% (Canada)' },
  AUD: { rate: 2.5, label: '2.5% (Australie)' },
}
