import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { motion } from 'framer-motion'
import { useAuthStore } from '@/stores/authStore'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useToast } from '@/hooks/use-toast'
import { Loader2, ArrowRight, Sparkles } from 'lucide-react'

const loginSchema = z.object({
  email: z.string().email('Email invalide'),
  password: z.string().min(1, 'Mot de passe requis'),
  mfaCode: z.string().optional(),
  rememberMe: z.boolean().optional(),
})

type LoginFormData = z.infer<typeof loginSchema>

const fieldClass =
  'h-12 rounded-xl border-border bg-secondary/40 px-4 text-base transition-colors focus-visible:ring-2 focus-visible:ring-primary focus-visible:border-primary/50'

export default function LoginPage() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const { login, isLoading, error, clearError } = useAuthStore()
  const [requiresMFA, setRequiresMFA] = useState(false)

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    defaultValues: { rememberMe: false },
  })

  const rememberMe = watch('rememberMe')

  const onSubmit = async (data: LoginFormData) => {
    clearError()
    try {
      await login(data.email, data.password, data.mfaCode, data.rememberMe)
      toast({ title: 'Connexion réussie', description: 'Bienvenue sur InvestAI' })
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

  const univers = ['Crypto', 'Actions', 'Crowdfunding', 'Prédictions']

  return (
    <div className="min-h-screen grid lg:grid-cols-[1.1fr_1fr] bg-background">
      {/* Left — immersive brand panel */}
      <div className="relative hidden overflow-hidden border-r border-border/60 lg:flex">
        <div className="absolute inset-0 mesh" />
        <div className="glow left-[-10%] top-[-10%] h-[420px] w-[420px] bg-[oklch(var(--primary))]" />
        <div className="glow bottom-[-15%] right-[-5%] h-[380px] w-[380px] bg-[oklch(var(--chart-3))]" />

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6 }}
          className="relative z-10 flex w-full flex-col justify-between p-14"
        >
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/15 ring-1 ring-primary/30">
              <Sparkles className="h-5 w-5 text-primary" strokeWidth={2} />
            </div>
            <span className="text-xl font-semibold tracking-tight">InvestAI</span>
          </div>

          {/* Narrative headline */}
          <div className="max-w-lg space-y-6">
            <div className="eyebrow text-primary">Votre patrimoine, une seule histoire</div>
            <h1 className="text-5xl font-semibold leading-[1.08] tracking-tight">
              Tout votre patrimoine,
              <br />
              <span className="gradient-text">lu d'un seul regard.</span>
            </h1>
            <p className="text-lg leading-relaxed text-muted-foreground">
              Crypto, actions, crowdfunding et prédictions réunis dans un récit clair —
              piloté par l'IA, sans le bruit.
            </p>

            {/* Univers pills */}
            <div className="flex flex-wrap gap-2 pt-2">
              {univers.map((u) => (
                <span
                  key={u}
                  className="rounded-full border border-border/70 bg-card/40 px-4 py-1.5 text-sm text-foreground/80 backdrop-blur-sm"
                >
                  {u}
                </span>
              ))}
            </div>
          </div>

          {/* Footer */}
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span className="inline-block h-2 w-2 rounded-full bg-[oklch(var(--gain))]" />
            Chiffrement de bout en bout · © 2026 InvestAI
          </div>
        </motion.div>
      </div>

      {/* Right — form */}
      <div className="relative flex items-center justify-center p-6 lg:p-12">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="w-full max-w-sm"
        >
          {/* Mobile logo */}
          <div className="mb-10 flex items-center gap-3 lg:hidden">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/15 ring-1 ring-primary/30">
              <Sparkles className="h-5 w-5 text-primary" strokeWidth={2} />
            </div>
            <span className="text-xl font-semibold tracking-tight">InvestAI</span>
          </div>

          {/* Header */}
          <div className="mb-8 space-y-2">
            <div className="eyebrow text-primary">Connexion</div>
            <h2 className="text-3xl font-semibold tracking-tight">Bon retour</h2>
            <p className="text-muted-foreground">Reprenez le fil de votre patrimoine.</p>
          </div>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="email" className="text-sm font-medium">
                Adresse email
              </Label>
              <Input
                id="email"
                type="email"
                placeholder="vous@exemple.com"
                className={fieldClass}
                autoComplete="email"
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
                  className="text-sm text-muted-foreground underline-offset-4 transition-colors hover:text-primary hover:underline"
                >
                  Oublié ?
                </Link>
              </div>
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                className={fieldClass}
                autoComplete="current-password"
                {...register('password')}
              />
              {errors.password && (
                <p className="text-sm text-destructive">{errors.password.message}</p>
              )}
            </div>

            <div className="flex items-center gap-2">
              <Checkbox
                id="rememberMe"
                checked={rememberMe}
                onCheckedChange={(checked) => setValue('rememberMe', checked === true)}
              />
              <Label htmlFor="rememberMe" className="cursor-pointer text-sm font-normal">
                Rester connecté
              </Label>
            </div>

            {requiresMFA && (
              <div className="space-y-2">
                <Label htmlFor="mfaCode" className="text-sm font-medium">
                  Code d'authentification
                </Label>
                <Input
                  id="mfaCode"
                  type="text"
                  placeholder="000000"
                  maxLength={6}
                  className="h-14 rounded-xl border-primary/40 bg-secondary/40 text-center text-2xl tracking-[0.5em] focus-visible:ring-2 focus-visible:ring-primary"
                  {...register('mfaCode')}
                />
                <p className="text-xs text-muted-foreground">
                  Saisissez le code de votre application TOTP.
                </p>
              </div>
            )}

            {error && (
              <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                {error}
              </div>
            )}

            <Button
              type="submit"
              className="group h-12 w-full rounded-xl bg-[linear-gradient(100deg,oklch(var(--primary)),oklch(var(--chart-3)))] text-base font-semibold text-primary-foreground shadow-[0_8px_30px_-8px_oklch(var(--primary)/0.7)] transition-all hover:shadow-[0_10px_40px_-6px_oklch(var(--primary)/0.85)]"
              disabled={isLoading}
            >
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  Connexion…
                </>
              ) : (
                <>
                  Se connecter
                  <ArrowRight className="ml-2 h-5 w-5 transition-transform group-hover:translate-x-0.5" />
                </>
              )}
            </Button>
          </form>

          {/* Register */}
          <p className="mt-8 text-center text-sm text-muted-foreground">
            Pas encore de compte ?{' '}
            <Link
              to="/register"
              className="font-medium text-primary underline-offset-4 hover:underline"
            >
              Ouvrir un compte
            </Link>
          </p>
        </motion.div>
      </div>
    </div>
  )
}
