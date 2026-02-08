import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useAuthStore } from '@/stores/authStore'
import { authApi } from '@/services/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { useToast } from '@/hooks/use-toast'
import {
  TrendingUp,
  Loader2,
  ArrowRight,
  Check,
  Sparkles,
  Target,
  Bell,
  Brain,
  Mail
} from 'lucide-react'

const registerSchema = z.object({
  email: z.string().email('Email invalide'),
  password: z.string().min(8, 'Le mot de passe doit contenir au moins 8 caractères'),
  confirmPassword: z.string(),
  firstName: z.string().optional(),
  lastName: z.string().optional(),
  acceptTerms: z.boolean().refine(val => val === true, {
    message: 'Vous devez accepter les conditions d\'utilisation',
  }),
}).refine((data) => data.password === data.confirmPassword, {
  message: 'Les mots de passe ne correspondent pas',
  path: ['confirmPassword'],
})

type RegisterFormData = z.infer<typeof registerSchema>

export default function RegisterPage() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const { setTokens, fetchUser } = useAuthStore()
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [registrationSuccess, setRegistrationSuccess] = useState(false)
  const [registeredEmail, setRegisteredEmail] = useState('')

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<RegisterFormData>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      acceptTerms: false,
    },
  })

  const acceptTerms = watch('acceptTerms')

  const onSubmit = async (data: RegisterFormData) => {
    setError(null)
    setIsLoading(true)

    try {
      const response = await authApi.register(
        data.email,
        data.password,
        data.firstName,
        data.lastName
      )

      // Check if email verification is required (new flow)
      if (response.email_verification_required) {
        setRegisteredEmail(data.email)
        setRegistrationSuccess(true)
        toast({
          title: 'Inscription réussie',
          description: 'Vérifiez votre email pour activer votre compte.',
        })
      } else if (response.access_token) {
        // Old flow (fallback)
        setTokens(response.access_token, response.refresh_token)
        await fetchUser()
        toast({
          title: 'Inscription réussie',
          description: 'Bienvenue sur InvestAI !',
        })
        navigate('/')
      }
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message :
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Une erreur est survenue lors de l\'inscription'
      setError(errorMessage)
      toast({
        variant: 'destructive',
        title: 'Erreur d\'inscription',
        description: errorMessage,
      })
    } finally {
      setIsLoading(false)
    }
  }

  const benefits = [
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

  // Show success screen after registration
  if (registrationSuccess) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background p-8">
        <div className="w-full max-w-md text-center space-y-6">
          <div className="mx-auto h-20 w-20 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
            <Mail className="h-10 w-10 text-green-600 dark:text-green-400" />
          </div>

          <div className="space-y-2">
            <h2 className="text-2xl font-bold">Vérifiez votre email</h2>
            <p className="text-muted-foreground">
              Nous avons envoyé un lien de vérification à
            </p>
            <p className="font-medium text-primary">{registeredEmail}</p>
          </div>

          <div className="p-4 rounded-lg bg-muted/50 text-sm text-muted-foreground">
            <p>Cliquez sur le lien dans l'email pour activer votre compte.</p>
            <p className="mt-2">Le lien est valable 24 heures.</p>
          </div>

          <div className="space-y-3">
            <Button
              variant="outline"
              className="w-full"
              onClick={() => navigate('/login')}
            >
              Aller à la connexion
            </Button>
            <p className="text-sm text-muted-foreground">
              Pas reçu d'email ?{' '}
              <button
                className="text-primary hover:underline"
                onClick={async () => {
                  try {
                    await authApi.resendVerification(registeredEmail)
                    toast({
                      title: 'Email envoyé',
                      description: 'Un nouveau lien de vérification a été envoyé.',
                    })
                  } catch {
                    toast({
                      variant: 'destructive',
                      title: 'Erreur',
                      description: 'Impossible d\'envoyer l\'email. Réessayez plus tard.',
                    })
                  }
                }}
              >
                Renvoyer le lien
              </button>
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex">
      {/* Left side - Registration form */}
      <div className="flex-1 flex items-center justify-center p-8 bg-background">
        <div className="w-full max-w-md space-y-6">
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
            <h2 className="text-3xl font-bold tracking-tight">Créer un compte</h2>
            <p className="mt-2 text-muted-foreground">
              Commencez à gérer vos investissements dès aujourd'hui
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="firstName" className="text-sm font-medium">
                  Prénom
                </Label>
                <Input
                  id="firstName"
                  type="text"
                  placeholder="Jean"
                  className="h-11 px-4"
                  {...register('firstName')}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="lastName" className="text-sm font-medium">
                  Nom
                </Label>
                <Input
                  id="lastName"
                  type="text"
                  placeholder="Dupont"
                  className="h-11 px-4"
                  {...register('lastName')}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="email" className="text-sm font-medium">
                Adresse email <span className="text-destructive">*</span>
              </Label>
              <Input
                id="email"
                type="email"
                placeholder="vous@exemple.com"
                className="h-11 px-4"
                {...register('email')}
              />
              {errors.email && (
                <p className="text-sm text-destructive">{errors.email.message}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="password" className="text-sm font-medium">
                Mot de passe <span className="text-destructive">*</span>
              </Label>
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                className="h-11 px-4"
                {...register('password')}
              />
              {errors.password && (
                <p className="text-sm text-destructive">{errors.password.message}</p>
              )}
              <p className="text-xs text-muted-foreground">
                Minimum 8 caractères
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="confirmPassword" className="text-sm font-medium">
                Confirmer le mot de passe <span className="text-destructive">*</span>
              </Label>
              <Input
                id="confirmPassword"
                type="password"
                placeholder="••••••••"
                className="h-11 px-4"
                {...register('confirmPassword')}
              />
              {errors.confirmPassword && (
                <p className="text-sm text-destructive">{errors.confirmPassword.message}</p>
              )}
            </div>

            <div className="flex items-start space-x-3 pt-2">
              <Checkbox
                id="acceptTerms"
                checked={acceptTerms}
                onCheckedChange={(checked) => setValue('acceptTerms', checked as boolean)}
              />
              <div className="grid gap-1.5 leading-none">
                <label
                  htmlFor="acceptTerms"
                  className="text-sm text-muted-foreground cursor-pointer"
                >
                  J'accepte les{' '}
                  <Link to="/terms" className="text-primary hover:underline">
                    conditions d'utilisation
                  </Link>{' '}
                  et la{' '}
                  <Link to="/privacy" className="text-primary hover:underline">
                    politique de confidentialité
                  </Link>
                </label>
                {errors.acceptTerms && (
                  <p className="text-sm text-destructive">{errors.acceptTerms.message}</p>
                )}
              </div>
            </div>

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
                  Création du compte...
                </>
              ) : (
                <>
                  Créer mon compte
                  <ArrowRight className="ml-2 h-5 w-5" />
                </>
              )}
            </Button>
          </form>

          {/* Login link */}
          <p className="text-center text-sm text-muted-foreground">
            Vous avez déjà un compte ?{' '}
            <Link to="/login" className="text-primary font-medium hover:underline">
              Se connecter
            </Link>
          </p>
        </div>
      </div>

      {/* Right side - Branding & Benefits */}
      <div className="hidden lg:flex lg:w-1/2 bg-gradient-to-bl from-primary/90 via-primary to-primary/80 relative overflow-hidden">
        {/* Background pattern */}
        <div className="absolute inset-0 opacity-10">
          <div className="absolute top-20 right-20 w-72 h-72 bg-white rounded-full blur-3xl" />
          <div className="absolute bottom-20 left-20 w-96 h-96 bg-white rounded-full blur-3xl" />
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
                Rejoignez des milliers<br />
                <span className="text-white/80">d'investisseurs</span>
              </h1>
              <p className="text-lg text-white/70 max-w-md">
                Créez votre compte gratuitement et prenez le contrôle
                de votre avenir financier.
              </p>
            </div>

            {/* Benefits list */}
            <div className="space-y-4">
              {benefits.map((benefit, index) => (
                <div
                  key={index}
                  className="flex items-center gap-4 p-4 rounded-xl bg-white/10 backdrop-blur border border-white/10"
                >
                  <div className="h-10 w-10 rounded-lg bg-white/20 flex items-center justify-center flex-shrink-0">
                    <benefit.icon className="h-5 w-5" />
                  </div>
                  <span className="font-medium">{benefit.text}</span>
                  <Check className="h-5 w-5 ml-auto text-green-300" />
                </div>
              ))}
            </div>

            {/* Stats */}
            <div className="grid grid-cols-3 gap-4 pt-4">
              <div className="text-center">
                <div className="text-3xl font-bold">100%</div>
                <div className="text-sm text-white/60">Gratuit</div>
              </div>
              <div className="text-center">
                <div className="text-3xl font-bold">24/7</div>
                <div className="text-sm text-white/60">Disponible</div>
              </div>
              <div className="text-center">
                <div className="text-3xl font-bold">SSL</div>
                <div className="text-sm text-white/60">Sécurisé</div>
              </div>
            </div>
          </div>

          {/* Footer */}
          <p className="text-white/50 text-sm">
            © 2025 InvestAI. Tous droits réservés.
          </p>
        </div>
      </div>
    </div>
  )
}
