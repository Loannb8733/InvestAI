import { Lightbulb } from 'lucide-react'
import PlannedOrdersSection from './decisions/PlannedOrdersSection'
import StrategiesSection from './decisions/StrategiesSection'

/**
 * Pilier « Décisions » du hub Intelligence — l'unique endroit où l'on AGIT.
 *
 * 1. Ordres planifiés (issus du rééquilibrage MPT et de la matrice de stratégie)
 * 2. Stratégies IA (cycle de vie complet + performance P&L)
 *
 * Pas de <h1> ni de bannière de régime : le hub parent fournit le chrome.
 */
export default function DecisionsPillar() {
  return (
    <div className="space-y-6">
      {/* Encart de liaison avec les autres piliers */}
      <div className="flex items-start gap-2 rounded-lg border border-accent/20 bg-accent/5 px-4 py-3">
        <Lightbulb className="h-4 w-4 text-accent mt-0.5 shrink-0" />
        <p className="text-sm text-muted-foreground">
          Les suggestions viennent des piliers{' '}
          <span className="font-medium text-foreground">Risque &amp; Performance</span> (rééquilibrage) et{' '}
          <span className="font-medium text-foreground">Marché &amp; Signaux</span> (alpha) — ici, on les
          planifie et on mesure ce qu'elles ont donné.
        </p>
      </div>

      <PlannedOrdersSection />
      <StrategiesSection />
    </div>
  )
}
