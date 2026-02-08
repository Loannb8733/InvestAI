import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useAuthStore } from '@/stores/authStore'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useToast } from '@/hooks/use-toast'
import {
  TrendingUp,
  Loader2,
  BarChart3,
  Shield,
  Zap,
  PieChart,
  ArrowRight
} from 'lucide-react'

const loginSchema = z.object({
  email: z.string().email('Email invalide'),
  password: z.string().min(1, 'Mot de passe requis'),
  mfaCode: z.string().optional(),
})

type LoginFormData = z.infer<typeof loginSchema>

export default function LoginPage() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const { login, isLoading, error, clearError } = useAuthStore()
  const [requiresMFA, setRequiresMFA] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
  })

  const onSubmit = async (data: LoginFormData) => {
    clearError()
    try {
      await login(data.email, data.password, data.mfaCode)
      toast({
        title: 'Connexion réussie',
        description: 'Bienvenue sur InvestAI',
      })
      navigate('/')
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Erreur inconnue'
      if (errorMessage.includes('MFA')) {
        setRequiresMFA(true)
      } else {
        toast({
          variant: 'destructive',
          title: 'Erreur de connexion',
          description: errorMessage,
        })
      }
    }
  }

  const features = [
    {
      icon: BarChart3,
      title: 'Analyses avancées',
      description: 'Visualisez vos performances en temps réel',
    },
    {
      icon: Shield,
      title: 'Sécurité maximale',
      description: 'Vos données sont chiffrées et protégées',
    },
    {
      icon: Zap,
      title: 'Synchronisation auto',
      description: 'Connectez vos exchanges en un clic',
    },
    {
      icon: PieChart,
      title: 'Diversification',
      description: 'Optimisez votre allocation d\'actifs',
    },
  ]

  return (
    <div className="min-h-screen flex">
      {/* Left side - Branding & Features */}
      <div className="hidden lg:flex lg:w-1/2 bg-gradient-to-br from-primary/90 via-primary to-primary/80 relative overflow-hidden">
        {/* Background pattern */}
        <div className="absolute inset-0 opacity-10">
          <div className="absolute top-20 left-20 w-72 h-72 bg-white rounded-full blur-3xl" />
          <div className="absolute bottom-20 right-20 w-96 h-96 bg-white rounded-full blur-3xl" />
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-white rounded-full blur-3xl opacity-5" />
        </div>

        {/* Content */}
        <div className="relative z-10 flex flex-col justify-between p-12 text-white">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="h-12 w-12 rounded-xl bg-white/20 backdrop-blur flex items-center justify-center">
              <TrendingUp className="h-7 w-7" />
            </div>
            <span className="text-2xl font-bold">InvestAI</span>
          </div>

          {/* Main content */}
          <div className="space-y-8">
            <div className="space-y-4">
              <h1 className="text-4xl font-bold leading-tight">
                Gérez vos investissements<br />
                <span className="text-white/80">intelligemment</span>
              </h1>
              <p className="text-lg text-white/70 max-w-md">
                La plateforme tout-en-un pour suivre, analyser et optimiser
                votre portefeuille d'investissement.
              </p>
            </div>

            {/* Features grid */}
            <div className="grid grid-cols-2 gap-4">
              {features.map((feature, index) => (
                <div
                  key={index}
                  className="p-4 rounded-xl bg-white/10 backdrop-blur border border-white/10 hover:bg-white/15 transition-colors"
                >
                  <feature.icon className="h-8 w-8 mb-3 text-white/90" />
                  <h3 className="font-semibold mb-1">{feature.title}</h3>
                  <p className="text-sm text-white/60">{feature.description}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Footer */}
          <p className="text-white/50 text-sm">
            © 2025 InvestAI. Tous droits réservés.
          </p>
        </div>
      </div>

      {/* Right side - Login form */}
      <div className="flex-1 flex items-center justify-center p-8 bg-background">
        <div className="w-full max-w-md space-y-8">
          {/* Mobile logo */}
          <div className="lg:hidden flex justify-center mb-8">
            <div className="flex items-center gap-3">
              <div className="h-12 w-12 rounded-xl bg-primary/20 flex items-center justify-center">
                <TrendingUp className="h-7 w-7 text-primary" />
              </div>
              <span className="text-2xl font-bold">InvestAI</span>
            </div>
          </div>

          {/* Header */}
          <div className="text-center lg:text-left">
            <h2 className="text-3xl font-bold tracking-tight">Bon retour !</h2>
            <p className="mt-2 text-muted-foreground">
              Connectez-vous pour accéder à votre tableau de bord
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="email" className="text-sm font-medium">
                Adresse email
              </Label>
              <Input
                id="email"
                type="email"
                placeholder="vous@exemple.com"
                className="h-12 px-4"
                {...register('email')}
              />
              {errors.email && (
                <p className="text-sm text-destructive">{errors.email.message}</p>
              )}
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="password" className="text-sm font-medium">
                  Mot de passe
                </Label>
                <Link
                  to="/forgot-password"
                  className="text-sm text-primary hover:underline"
                >
                  Mot de passe oublié ?
                </Link>
              </div>
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                className="h-12 px-4"
                {...register('password')}
              />
              {errors.password && (
                <p className="text-sm text-destructive">{errors.password.message}</p>
              )}
            </div>

            {requiresMFA && (
              <div className="space-y-2">
                <Label htmlFor="mfaCode" className="text-sm font-medium">
                  Code d'authentification
                </Label>
                <Input
                  id="mfaCode"
                  type="text"
                  placeholder="123456"
                  maxLength={6}
                  className="h-12 px-4 text-center text-2xl tracking-[0.5em] font-mono"
                  {...register('mfaCode')}
                />
                <p className="text-xs text-muted-foreground text-center">
                  Entrez le code de votre application d'authentification
                </p>
              </div>
            )}

            {error && (
              <div className="p-4 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">
                {error}
              </div>
            )}

            <Button
              type="submit"
              className="w-full h-12 text-base font-semibold"
              disabled={isLoading}
            >
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  Connexion en cours...
                </>
              ) : (
                <>
                  Se connecter
                  <ArrowRight className="ml-2 h-5 w-5" />
                </>
              )}
            </Button>
          </form>

          {/* Divider */}
          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-background px-2 text-muted-foreground">
                Nouveau sur InvestAI ?
              </span>
            </div>
          </div>

          {/* Register link */}
          <Link to="/register">
            <Button variant="outline" className="w-full h-12 text-base">
              Créer un compte gratuit
            </Button>
          </Link>
        </div>
      </div>
    </div>
  )
}
