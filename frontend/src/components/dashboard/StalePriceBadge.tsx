import { Badge } from '@/components/ui/badge'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { WifiOff, AlertTriangle } from 'lucide-react'

interface StalePriceBadgeProps {
  wsConnected: boolean
  forexStale?: boolean
}

export default function StalePriceBadge({ wsConnected, forexStale }: StalePriceBadgeProps) {
  if (wsConnected && !forexStale) return null

  return (
    <div className="flex items-center gap-2">
      {!wsConnected && (
        <TooltipProvider delayDuration={100}>
          <Tooltip>
            <TooltipTrigger asChild>
              <Badge variant="outline" className="text-amber-600 border-amber-500/50 bg-amber-500/10 gap-1 text-xs">
                <WifiOff className="h-3 w-3" />
                Prix fig&eacute;s
              </Badge>
            </TooltipTrigger>
            <TooltipContent>
              <p className="text-sm">Connexion temps r&eacute;el interrompue. Les prix affich&eacute;s peuvent &ecirc;tre obsol&egrave;tes.</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      )}
      {forexStale && (
        <TooltipProvider delayDuration={100}>
          <Tooltip>
            <TooltipTrigger asChild>
              <Badge variant="outline" className="text-orange-600 border-orange-500/50 bg-orange-500/10 gap-1 text-xs">
                <AlertTriangle className="h-3 w-3" />
                Taux de change anciens
              </Badge>
            </TooltipTrigger>
            <TooltipContent>
              <p className="text-sm">Les taux de change datent de plus de 24h. Les montants convertis sont approximatifs.</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      )}
    </div>
  )
}
