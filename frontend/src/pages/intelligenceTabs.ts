import type { LucideIcon } from 'lucide-react'
import { Bell, Crosshair, Radar, ShieldHalf } from 'lucide-react'

/**
 * Les 4 piliers du hub Intelligence, dans leur ordre d'affichage.
 *
 * Extraits du composant pour rester importables par les tests (et par tout
 * code qui construit un lien vers un onglet) sans casser le Fast Refresh :
 * un fichier .tsx qui exporte autre chose que des composants force un reload
 * complet à chaque édition.
 */
export const TABS = [
  { value: 'risk', label: 'Risque & Performance', icon: ShieldHalf },
  { value: 'market', label: 'Marché & Signaux', icon: Radar },
  { value: 'decisions', label: 'Décisions', icon: Crosshair },
  { value: 'alerts', label: 'Alertes', icon: Bell },
] as const satisfies ReadonlyArray<{ value: string; label: string; icon: LucideIcon }>

/** Anciens ?tab= (liens externes, favoris) → nouveaux piliers. */
export const LEGACY_TAB_MAP: Record<string, string> = {
  alpha: 'market',
  smart: 'risk',
  analytics: 'risk',
  predictions: 'market',
  strategies: 'decisions',
  alerts: 'alerts',
}
