import { Download, Key, RefreshCw, Trash2, type LucideIcon } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

interface Step {
  icon: LucideIcon
  circle: string
  iconColor: string
  title: string
  text: string
}

const STEPS: Step[] = [
  {
    icon: Key,
    circle: 'bg-muted',
    iconColor: 'text-muted-foreground',
    title: 'Tester',
    text: 'Vérifie que vos clés API fonctionnent et affiche vos soldes actuels.',
  },
  {
    icon: RefreshCw,
    circle: 'bg-muted',
    iconColor: 'text-muted-foreground',
    title: 'Sync',
    text: "Met à jour les quantités de vos actifs depuis l'exchange.",
  },
  {
    icon: Download,
    circle: 'bg-primary/20',
    iconColor: 'text-primary',
    title: 'Import',
    text: "Importe l'historique complet : trades, achats fiat, rewards et staking.",
  },
  {
    icon: Trash2,
    circle: 'bg-destructive/20',
    iconColor: 'text-destructive',
    title: 'Supprimer',
    text: "Retire la connexion. Vos données importées restent dans l'app.",
  },
]

export default function HowItWorksCard() {
  return (
    <Card elevation="raised" className="bg-muted/30">
      <CardHeader>
        <CardTitle className="text-lg">Comment ça marche ?</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map(({ icon: Icon, circle, iconColor, title, text }) => (
            <div key={title} className="space-y-2">
              <div className="flex items-center gap-2">
                <div className={`h-8 w-8 rounded-full ${circle} flex items-center justify-center`}>
                  <Icon className={`h-4 w-4 ${iconColor}`} />
                </div>
                <span className="font-medium">{title}</span>
              </div>
              <p className="text-sm text-muted-foreground">{text}</p>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
