import { Bell, Brain, Check, Sparkles, Target, TrendingUp } from 'lucide-react'
import AuroraCanvas from '@/components/ui/aurora-canvas'

const BENEFITS = [
  {
    icon: Sparkles,
    text: 'Suivi de portefeuille en temps réel',
  },
  {
    icon: Target,
    text: 'Analyses et rapports détaillés',
  },
  {
    icon: Bell,
    text: 'Alertes de prix personnalisées',
  },
  {
    icon: Brain,
    text: 'Prédictions basées sur l\'IA',
  },
]

export default function RegisterBrandPanel() {
  return (
      <div className="hidden lg:flex lg:w-1/2 bg-primary relative overflow-hidden border-l border-border">
        <AuroraCanvas className="opacity-40" />
        <div className="relative z-10 flex flex-col justify-between p-12 text-primary-foreground">
          <div className="flex items-center gap-3">
            <div className="h-12 w-12 rounded-lg bg-primary-foreground/10 flex items-center justify-center">
              <TrendingUp className="h-7 w-7" strokeWidth={1.5} />
            </div>
            <span className="font-serif text-2xl font-medium tracking-tight">InvestAI</span>
          </div>

          <div className="space-y-8">
            <div className="space-y-4">
              <h1 className="font-serif text-4xl font-medium leading-tight tracking-tight">
                Rejoignez des milliers<br />
                <span className="text-primary-foreground/70">d'investisseurs</span>
              </h1>
              <p className="text-lg text-primary-foreground/70 max-w-md">
                Créez votre compte gratuitement et prenez le contrôle
                de votre avenir financier.
              </p>
            </div>

            <div className="space-y-4">
              {BENEFITS.map((benefit) => (
                <div
                  key={benefit.text}
                  className="flex items-center gap-4 p-4 rounded-lg bg-primary-foreground/5 border border-primary-foreground/10"
                >
                  <div className="h-10 w-10 rounded-lg bg-primary-foreground/10 flex items-center justify-center shrink-0">
                    <benefit.icon className="h-5 w-5" strokeWidth={1.5} />
                  </div>
                  <span className="font-medium">{benefit.text}</span>
                  <Check className="h-5 w-5 ml-auto text-gain" strokeWidth={1.5} />
                </div>
              ))}
            </div>

            <div className="grid grid-cols-3 gap-4 pt-4">
              <div className="text-center">
                <div className="text-3xl font-serif font-medium">100%</div>
                <div className="text-sm text-primary-foreground/60">Gratuit</div>
              </div>
              <div className="text-center">
                <div className="text-3xl font-serif font-medium">24/7</div>
                <div className="text-sm text-primary-foreground/60">Disponible</div>
              </div>
              <div className="text-center">
                <div className="text-3xl font-serif font-medium">SSL</div>
                <div className="text-sm text-primary-foreground/60">Sécurisé</div>
              </div>
            </div>
          </div>

          <p className="text-primary-foreground/50 text-sm">
            © 2026 InvestAI. Tous droits réservés.
          </p>
        </div>
      </div>
  )
}
