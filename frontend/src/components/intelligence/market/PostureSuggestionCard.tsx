import { Badge } from '@/components/ui/badge'
import { Lightbulb } from 'lucide-react'
import type { MarketCycleData } from '@/types/predictions'

/**
 * Carte compacte « Suggestion de posture ».
 *
 * Remplace les grandes bannières de régime prescriptives de l'ancienne page
 * Prédictions (« Mode Accumulation », « Mode Distribution — sécurisez 20-30 % »…)
 * et les bandeaux de contexte de la Matrice de Stratégie. Le régime lui-même
 * est affiché UNE fois par RegimeHeader (partagé) ; ici on ne garde que la
 * recommandation actionnable, étiquetée avec sa confiance — jamais présentée
 * comme un ordre.
 */

interface Posture {
  title: string
  text: string
  toneClasses: string
}

const POSTURES: Record<string, Posture> = {
  bearish: {
    title: 'Accumulation progressive',
    text:
      'Les prix sont décotés — historiquement une zone favorable au DCA/VCA sur les actifs à fort alpha. ' +
      'Les signaux de vente sont à relativiser dans cette phase.',
    toneClasses: 'border-accent/30 bg-accent/5',
  },
  bullish: {
    title: 'Préparer les prises de profits',
    text:
      'Marché en phase haussière — laissez courir les positions mais préparez vos niveaux de sortie : ' +
      'gains partiels sécurisés et stop-loss remontés.',
    toneClasses: 'border-warning/30 bg-warning/5',
  },
  top: {
    title: 'Sécuriser une partie des gains',
    text:
      'Signes de sommet détectés — envisagez de sécuriser une partie des gains et de garder du cash ' +
      'pour accumuler au prochain creux.',
    toneClasses: 'border-loss/30 bg-loss/5',
  },
}
POSTURES.topping = POSTURES.top
POSTURES.distribution = POSTURES.top
POSTURES.markup = POSTURES.bullish
POSTURES.markdown = POSTURES.bearish
POSTURES.accumulation = POSTURES.bearish

interface PostureSuggestionCardProps {
  marketCycle: MarketCycleData | undefined
}

export default function PostureSuggestionCard({ marketCycle }: PostureSuggestionCardProps) {
  const regime = marketCycle?.market_regime
  const confidence = regime?.confidence ?? 0
  const posture = regime ? POSTURES[regime.dominant_regime] : undefined

  // Même seuil que les anciennes bannières : en-dessous de 50 % de confiance,
  // on n'affiche aucune suggestion (signal trop incertain).
  if (!posture || confidence <= 0.5) return null

  return (
    <div className={`rounded-lg border p-3 flex items-start gap-3 ${posture.toneClasses}`}>
      <Lightbulb className="h-4 w-4 mt-0.5 shrink-0 text-muted-foreground" aria-hidden />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium flex items-center gap-2 flex-wrap">
          <span className="text-xs uppercase tracking-wide text-muted-foreground">
            Suggestion de posture
          </span>
          {posture.title}
          <Badge variant="secondary" className="text-xs">
            Confiance {(confidence * 100).toFixed(0)} %
          </Badge>
        </p>
        <p className="text-xs text-muted-foreground mt-1">
          {posture.text} Suggestion statistique — pas un conseil d'investissement.
        </p>
      </div>
    </div>
  )
}
