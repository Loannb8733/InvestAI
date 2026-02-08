import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import {
  Wallet,
  BarChart3,
  Shield,
  ChevronRight,
  ChevronLeft,
  Check,
  TrendingUp,
  PieChart,
  FileText,
} from 'lucide-react'

const STORAGE_KEY = 'investai-onboarding-done'

export function useOnboarding() {
  const done = localStorage.getItem(STORAGE_KEY) === 'true'
  const markDone = () => localStorage.setItem(STORAGE_KEY, 'true')
  return { showOnboarding: !done, markDone }
}

const steps = [
  {
    title: 'Bienvenue sur InvestAI',
    description: 'Votre plateforme de gestion et d\'analyse d\'investissements. Suivez ce guide pour bien commencer.',
    icon: TrendingUp,
    content: (
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          {[
            { icon: Wallet, label: 'Crypto', desc: 'Bitcoin, Ethereum...' },
            { icon: BarChart3, label: 'Actions', desc: 'Apple, Tesla...' },
            { icon: PieChart, label: 'ETF', desc: 'S&P 500, MSCI World...' },
            { icon: Shield, label: 'Immobilier', desc: 'SCPI, biens physiques' },
          ].map((item) => (
            <div key={item.label} className="flex items-center gap-3 p-3 rounded-lg border bg-muted/50">
              <item.icon className="h-5 w-5 text-primary shrink-0" />
              <div>
                <p className="text-sm font-medium">{item.label}</p>
                <p className="text-xs text-muted-foreground">{item.desc}</p>
              </div>
            </div>
          ))}
        </div>
        <p className="text-sm text-muted-foreground">
          InvestAI supporte tous ces types d'actifs dans un seul tableau de bord unifié.
        </p>
      </div>
    ),
  },
  {
    title: 'Ajoutez votre premier portefeuille',
    description: 'Commencez par créer un portefeuille et y ajouter vos actifs.',
    icon: Wallet,
    content: (
      <div className="space-y-4">
        <ol className="space-y-3">
          {[
            'Allez dans Portfolio et cliquez "Nouveau portefeuille"',
            'Donnez-lui un nom (ex: "Crypto", "Actions PEA")',
            'Ajoutez vos actifs avec leur quantité et prix d\'achat',
            'Ajoutez vos transactions pour un suivi précis',
          ].map((step, i) => (
            <li key={i} className="flex items-start gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-bold">
                {i + 1}
              </span>
              <span className="text-sm">{step}</span>
            </li>
          ))}
        </ol>
        <div className="rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
          <p className="text-xs text-blue-500">
            Astuce : Connectez vos exchanges (Binance, Kraken...) via la page Exchanges pour importer automatiquement vos positions.
          </p>
        </div>
      </div>
    ),
  },
  {
    title: 'Suivez votre performance',
    description: 'Le tableau de bord vous donne une vue globale de votre patrimoine.',
    icon: BarChart3,
    content: (
      <div className="space-y-4">
        <div className="space-y-2">
          {[
            { label: 'Dashboard', desc: 'Vue globale : valeur totale, plus-values, graphiques' },
            { label: 'Analyses', desc: 'Sharpe, Sortino, VaR, corrélations, Monte Carlo, Beta' },
            { label: 'Prédictions IA', desc: 'Prévisions de prix par ensemble de modèles (Prophet, XGBoost, ARIMA)' },
            { label: 'Simulations', desc: 'FIRE, projections, DCA — testez vos stratégies' },
          ].map((item) => (
            <div key={item.label} className="flex items-start gap-2 p-2 rounded border">
              <ChevronRight className="h-4 w-4 text-primary mt-0.5 shrink-0" />
              <div>
                <span className="text-sm font-medium">{item.label}</span>
                <span className="text-xs text-muted-foreground ml-1">— {item.desc}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    ),
  },
  {
    title: 'Rapports et fiscalité',
    description: 'Générez vos rapports de performance et vos déclarations fiscales.',
    icon: FileText,
    content: (
      <div className="space-y-4">
        <div className="space-y-2">
          {[
            { label: 'Rapport de performance', desc: 'PDF/Excel avec toutes vos métriques' },
            { label: 'Déclaration fiscale 2086', desc: 'Plus-values crypto calculées selon la méthode PMP imposée par le fisc' },
            { label: 'Estimation d\'impôt', desc: 'Flat tax 30% (12.8% IR + 17.2% PS) automatiquement calculée' },
            { label: 'Alertes', desc: 'Configurez des alertes de prix et de performance' },
          ].map((item) => (
            <div key={item.label} className="flex items-start gap-2 p-2 rounded border">
              <Check className="h-4 w-4 text-green-500 mt-0.5 shrink-0" />
              <div>
                <span className="text-sm font-medium">{item.label}</span>
                <span className="text-xs text-muted-foreground ml-1">— {item.desc}</span>
              </div>
            </div>
          ))}
        </div>
        <div className="rounded-lg border border-green-500/20 bg-green-500/5 p-3">
          <p className="text-xs text-green-500">
            Tout est prêt ! Cliquez "Commencer" pour accéder à votre tableau de bord.
          </p>
        </div>
      </div>
    ),
  },
]

export default function OnboardingWizard({ onComplete }: { onComplete: () => void }) {
  const [step, setStep] = useState(0)
  const navigate = useNavigate()
  const current = steps[step]
  const Icon = current.icon
  const isLast = step === steps.length - 1

  const handleComplete = () => {
    localStorage.setItem(STORAGE_KEY, 'true')
    onComplete()
    navigate('/portfolio')
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
      <Card className="w-full max-w-lg mx-4 shadow-2xl">
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
              <Icon className="h-5 w-5 text-primary" />
            </div>
            <div>
              <CardTitle className="text-lg">{current.title}</CardTitle>
              <CardDescription>{current.description}</CardDescription>
            </div>
          </div>
          {/* Progress dots */}
          <div className="flex gap-1.5 pt-3">
            {steps.map((_, i) => (
              <div
                key={i}
                className={`h-1.5 flex-1 rounded-full transition-colors ${
                  i <= step ? 'bg-primary' : 'bg-muted'
                }`}
              />
            ))}
          </div>
        </CardHeader>
        <CardContent>
          <div className="min-h-[240px]">{current.content}</div>
          <div className="flex items-center justify-between pt-4 border-t mt-4">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setStep((s) => s - 1)}
              disabled={step === 0}
            >
              <ChevronLeft className="h-4 w-4 mr-1" />
              Précédent
            </Button>
            <span className="text-xs text-muted-foreground">
              {step + 1} / {steps.length}
            </span>
            {isLast ? (
              <Button size="sm" onClick={handleComplete}>
                Commencer
                <Check className="h-4 w-4 ml-1" />
              </Button>
            ) : (
              <Button size="sm" onClick={() => setStep((s) => s + 1)}>
                Suivant
                <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            )}
          </div>
          {/* Skip link */}
          <div className="text-center pt-2">
            <button
              className="text-xs text-muted-foreground hover:text-foreground transition-colors"
              onClick={handleComplete}
            >
              Passer le guide
            </button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
