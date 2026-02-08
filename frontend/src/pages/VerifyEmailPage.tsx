import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { authApi } from '@/services/api'
import { Button } from '@/components/ui/button'
import { useToast } from '@/hooks/use-toast'
import {
  TrendingUp,
  Loader2,
  CheckCircle2,
  XCircle,
  ArrowRight
} from 'lucide-react'

export default function VerifyEmailPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { toast } = useToast()
  const { setTokens, fetchUser } = useAuthStore()

  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [errorMessage, setErrorMessage] = useState('')

  useEffect(() => {
    const verifyEmail = async () => {
      const token = searchParams.get('token')

      if (!token) {
        setStatus('error')
        setErrorMessage('Lien de vérification invalide.')
        return
      }

      try {
        const response = await authApi.verifyEmail(token)

        // Auto-login after verification
        if (response.access_token) {
          setTokens(response.access_token, response.refresh_token)
          await fetchUser()
        }

        setStatus('success')
        toast({
          title: 'Email vérifié',
          description: 'Votre compte a été activé avec succès !',
        })
      } catch (err: unknown) {
        setStatus('error')
        const message = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          'Le lien de vérification est invalide ou a expiré.'
        setErrorMessage(message)
      }
    }

    verifyEmail()
  }, [searchParams, setTokens, fetchUser, toast])

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-8">
      <div className="w-full max-w-md text-center space-y-6">
        {/* Logo */}
        <div className="flex justify-center mb-8">
          <div className="flex items-center gap-3">
            <div className="h-12 w-12 rounded-xl bg-primary/20 flex items-center justify-center">
              <TrendingUp className="h-7 w-7 text-primary" />
            </div>
            <span className="text-2xl font-bold">InvestAI</span>
          </div>
        </div>

        {status === 'loading' && (
          <>
            <div className="mx-auto h-20 w-20 rounded-full bg-primary/10 flex items-center justify-center">
              <Loader2 className="h-10 w-10 text-primary animate-spin" />
            </div>
            <div className="space-y-2">
              <h2 className="text-2xl font-bold">Vérification en cours...</h2>
              <p className="text-muted-foreground">
                Veuillez patienter pendant que nous vérifions votre email.
              </p>
            </div>
          </>
        )}

        {status === 'success' && (
          <>
            <div className="mx-auto h-20 w-20 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
              <CheckCircle2 className="h-10 w-10 text-green-600 dark:text-green-400" />
            </div>
            <div className="space-y-2">
              <h2 className="text-2xl font-bold">Email vérifié !</h2>
              <p className="text-muted-foreground">
                Votre compte a été activé avec succès.
                Vous pouvez maintenant accéder à toutes les fonctionnalités.
              </p>
            </div>
            <Button
              className="w-full"
              onClick={() => navigate('/')}
            >
              Accéder à mon tableau de bord
              <ArrowRight className="ml-2 h-5 w-5" />
            </Button>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="mx-auto h-20 w-20 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
              <XCircle className="h-10 w-10 text-red-600 dark:text-red-400" />
            </div>
            <div className="space-y-2">
              <h2 className="text-2xl font-bold">Vérification échouée</h2>
              <p className="text-muted-foreground">
                {errorMessage}
              </p>
            </div>
            <div className="space-y-3">
              <Button
                variant="outline"
                className="w-full"
                onClick={() => navigate('/register')}
              >
                S'inscrire à nouveau
              </Button>
              <p className="text-sm text-muted-foreground">
                Vous avez déjà un compte ?{' '}
                <Link to="/login" className="text-primary hover:underline">
                  Se connecter
                </Link>
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
