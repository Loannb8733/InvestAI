import { useState, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuthStore } from '@/stores/authStore'
import { useTheme } from '@/components/theme-provider'
import { authApi, profileApi, investorProfileQueryKey, type RiskProfile } from '@/services/api'
import { useToast } from '@/hooks/use-toast'
import { Shield, User, Moon, Sun, Key, Loader2, Globe, TrendingUp } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const CURRENCIES = [
  { value: 'EUR', label: 'EUR (€)', symbol: '€' },
  { value: 'USD', label: 'USD ($)', symbol: '$' },
  { value: 'CHF', label: 'CHF (CHF)', symbol: 'CHF' },
  { value: 'GBP', label: 'GBP (£)', symbol: '£' },
]

// Tranches marginales d'imposition (barème IR français). Les values doivent
// correspondre à String(tmi_rate) renvoyé par l'API (0.3 et non 0.30).
const TMI_OPTIONS = [
  { value: '0', label: '0 %' },
  { value: '0.11', label: '11 %' },
  { value: '0.3', label: '30 %' },
  { value: '0.41', label: '41 %' },
  { value: '0.45', label: '45 %' },
]

const RISK_OPTIONS: { value: RiskProfile; label: string }[] = [
  { value: 'conservative', label: 'Prudent' },
  { value: 'moderate', label: 'Modéré' },
  { value: 'aggressive', label: 'Agressif' },
]

export default function SettingsPage() {
  const user = useAuthStore((state) => state.user)
  const fetchCurrentUser = useAuthStore((state) => state.fetchCurrentUser)
  const { theme, setTheme } = useTheme()
  const { toast } = useToast()

  // Profile form state — kept in sync with store after successful save
  const [firstName, setFirstName] = useState(user?.firstName || '')
  const [lastName, setLastName] = useState(user?.lastName || '')
  const [preferredCurrency, setPreferredCurrency] = useState(user?.preferredCurrency || 'EUR')

  useEffect(() => {
    if (user) {
      setFirstName(user.firstName || '')
      setLastName(user.lastName || '')
      setPreferredCurrency(user.preferredCurrency || 'EUR')
    }
  }, [user])

  // Investor profile form state — hydraté depuis l'API
  const queryClient = useQueryClient()
  const [tmiRate, setTmiRate] = useState('')
  const [riskProfile, setRiskProfile] = useState('')
  const [monthlyDca, setMonthlyDca] = useState('')

  const { data: investorProfile } = useQuery({
    queryKey: investorProfileQueryKey,
    queryFn: profileApi.getInvestorProfile,
    staleTime: 60_000,
  })

  useEffect(() => {
    if (investorProfile) {
      setTmiRate(investorProfile.tmi_rate != null ? String(investorProfile.tmi_rate) : '')
      setRiskProfile(investorProfile.risk_profile ?? '')
      setMonthlyDca(investorProfile.monthly_dca_eur != null ? String(investorProfile.monthly_dca_eur) : '')
    }
  }, [investorProfile])

  // Password form state
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  // MFA state
  const [mfaDialogOpen, setMfaDialogOpen] = useState(false)
  const [mfaQrCode, setMfaQrCode] = useState('')
  const [mfaSecret, setMfaSecret] = useState('')
  const [mfaCode, setMfaCode] = useState('')

  // Profile mutation
  const profileMutation = useMutation({
    mutationFn: () => profileApi.updateProfile({ first_name: firstName, last_name: lastName, preferred_currency: preferredCurrency }),
    onSuccess: () => {
      fetchCurrentUser()
      toast({ title: 'Profil mis à jour', description: 'Vos informations ont été enregistrées.' })
    },
    onError: () => {
      toast({ title: 'Erreur', description: 'Impossible de mettre à jour le profil.', variant: 'destructive' })
    },
  })

  // Investor profile mutation
  const investorMutation = useMutation({
    mutationFn: () =>
      profileApi.updateInvestorProfile({
        tmi_rate: tmiRate === '' ? null : Number(tmiRate),
        risk_profile: riskProfile === '' ? null : (riskProfile as RiskProfile),
        monthly_dca_eur: monthlyDca === '' ? null : Number(monthlyDca),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: investorProfileQueryKey })
      toast({ title: 'Profil investisseur mis à jour', description: 'Vos paramètres financiers ont été enregistrés.' })
    },
    onError: () => {
      toast({ title: 'Erreur', description: "Impossible d'enregistrer le profil investisseur.", variant: 'destructive' })
    },
  })

  const handleInvestorSave = () => {
    if (monthlyDca !== '') {
      const dca = Number(monthlyDca)
      if (!Number.isFinite(dca) || dca < 0) {
        toast({ title: 'Montant invalide', description: 'Le DCA mensuel doit être un montant positif ou nul.', variant: 'destructive' })
        return
      }
    }
    investorMutation.mutate()
  }

  // Password mutation
  const passwordMutation = useMutation({
    mutationFn: () => profileApi.changePassword(currentPassword, newPassword),
    onSuccess: () => {
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      toast({ title: 'Mot de passe modifié', description: 'Votre mot de passe a été mis à jour.' })
    },
    onError: () => {
      toast({ title: 'Erreur', description: 'Mot de passe actuel incorrect.', variant: 'destructive' })
    },
  })

  // MFA setup mutation
  const mfaSetupMutation = useMutation({
    mutationFn: () => authApi.setupMFA(),
    onSuccess: (data: { qr_code: string; secret: string }) => {
      setMfaQrCode(data.qr_code)
      setMfaSecret(data.secret)
      setMfaDialogOpen(true)
    },
    onError: () => {
      toast({ title: 'Erreur', description: 'Impossible de configurer la MFA.', variant: 'destructive' })
    },
  })

  // MFA verify mutation
  const mfaVerifyMutation = useMutation({
    mutationFn: () => authApi.verifyMFA(mfaCode),
    onSuccess: () => {
      setMfaDialogOpen(false)
      setMfaCode('')
      fetchCurrentUser()
      toast({ title: 'MFA activée', description: "L'authentification à deux facteurs est maintenant active." })
    },
    onError: () => {
      toast({ title: 'Code invalide', description: 'Veuillez vérifier le code et réessayer.', variant: 'destructive' })
    },
  })

  // MFA disable mutation
  const mfaDisableMutation = useMutation({
    mutationFn: () => authApi.disableMFA(mfaCode),
    onSuccess: () => {
      setMfaDialogOpen(false)
      setMfaCode('')
      fetchCurrentUser()
      toast({ title: 'MFA désactivée', description: "L'authentification à deux facteurs a été désactivée." })
    },
    onError: () => {
      toast({ title: 'Code invalide', description: 'Veuillez vérifier le code et réessayer.', variant: 'destructive' })
    },
  })

  const handlePasswordChange = () => {
    if (newPassword !== confirmPassword) {
      toast({ title: 'Erreur', description: 'Les mots de passe ne correspondent pas.', variant: 'destructive' })
      return
    }
    if (newPassword.length < 10 || !/[A-Z]/.test(newPassword) || !/\d/.test(newPassword)) {
      toast({ title: 'Erreur', description: 'Le mot de passe doit contenir au moins 10 caractères, une majuscule et un chiffre.', variant: 'destructive' })
      return
    }
    passwordMutation.mutate()
  }

  const handleMfaToggle = () => {
    if (user?.mfaEnabled) {
      setMfaDialogOpen(true)
    } else {
      mfaSetupMutation.mutate()
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-serif font-medium">Paramètres</h1>

      <div className="grid gap-6">
        {/* Profile */}
        <Card elevation="raised">
          <CardHeader>
            <div className="flex items-center gap-2">
              <User className="h-5 w-5" />
              <CardTitle>Profil</CardTitle>
            </div>
            <CardDescription>Gérez vos informations personnelles</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" value={user?.email || ''} disabled />
              </div>
              <div className="space-y-2">
                <Label htmlFor="role">Rôle</Label>
                <Input id="role" value={user?.role || ''} disabled className="capitalize" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="firstName">Prénom</Label>
                <Input
                  id="firstName"
                  placeholder="Votre prénom"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="lastName">Nom</Label>
                <Input
                  id="lastName"
                  placeholder="Votre nom"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="currency" className="flex items-center gap-1">
                <Globe className="h-4 w-4" />
                Devise préférée
              </Label>
              <Select value={preferredCurrency} onValueChange={setPreferredCurrency}>
                <SelectTrigger className="w-48">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CURRENCIES.map((c) => (
                    <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">Tous les montants seront affichés dans cette devise</p>
            </div>
            <Button
              onClick={() => profileMutation.mutate()}
              disabled={profileMutation.isPending}
            >
              {profileMutation.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Enregistrer les modifications
            </Button>
          </CardContent>
        </Card>

        {/* Investor profile */}
        <Card elevation="raised">
          <CardHeader>
            <div className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5" />
              <CardTitle>Profil investisseur</CardTitle>
            </div>
            <CardDescription>
              Vos paramètres financiers — utilisés par le dashboard, les suggestions et les simulateurs
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="tmiRate">Tranche marginale d'imposition (TMI)</Label>
                <Select value={tmiRate} onValueChange={setTmiRate}>
                  <SelectTrigger id="tmiRate">
                    <SelectValue placeholder="Non renseignée" />
                  </SelectTrigger>
                  <SelectContent>
                    {TMI_OPTIONS.map((o) => (
                      <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  Utilisée par l'estimation d'impôt au barème progressif (dashboard)
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="riskProfile">Profil de risque</Label>
                <Select value={riskProfile} onValueChange={setRiskProfile}>
                  <SelectTrigger id="riskProfile">
                    <SelectValue placeholder="Non renseigné" />
                  </SelectTrigger>
                  <SelectContent>
                    {RISK_OPTIONS.map((o) => (
                      <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  Utilisé par les suggestions de déploiement de capital
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="monthlyDca">DCA mensuel (€)</Label>
                <Input
                  id="monthlyDca"
                  type="number"
                  min={0}
                  step={50}
                  inputMode="decimal"
                  placeholder="ex : 500"
                  value={monthlyDca}
                  onChange={(e) => setMonthlyDca(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  Pré-remplit les simulateurs de projection
                </p>
              </div>
            </div>
            <Button onClick={handleInvestorSave} disabled={investorMutation.isPending}>
              {investorMutation.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Enregistrer le profil investisseur
            </Button>
          </CardContent>
        </Card>

        {/* Security */}
        <Card elevation="raised">
          <CardHeader>
            <div className="flex items-center gap-2">
              <Shield className="h-5 w-5" />
              <CardTitle>Sécurité</CardTitle>
            </div>
            <CardDescription>Gérez la sécurité de votre compte</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between p-4 border rounded-lg">
              <div>
                <p className="font-medium">Authentification à deux facteurs (MFA)</p>
                <p className="text-sm text-muted-foreground">
                  {user?.mfaEnabled
                    ? 'La MFA est activée sur votre compte'
                    : 'Protégez votre compte avec une authentification supplémentaire'}
                </p>
              </div>
              <Button
                variant={user?.mfaEnabled ? 'destructive' : 'default'}
                onClick={handleMfaToggle}
                disabled={mfaSetupMutation.isPending}
              >
                {mfaSetupMutation.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                {user?.mfaEnabled ? 'Désactiver' : 'Activer'}
              </Button>
            </div>
            <div className="space-y-2">
              <Label htmlFor="currentPassword">Mot de passe actuel</Label>
              <Input
                id="currentPassword"
                type="password"
                placeholder="••••••••"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
              />
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="newPassword">Nouveau mot de passe</Label>
                <Input
                  id="newPassword"
                  type="password"
                  placeholder="••••••••"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="confirmPassword">Confirmer le mot de passe</Label>
                <Input
                  id="confirmPassword"
                  type="password"
                  placeholder="••••••••"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
              </div>
            </div>
            <Button
              onClick={handlePasswordChange}
              disabled={passwordMutation.isPending || !currentPassword || !newPassword}
            >
              {passwordMutation.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Changer le mot de passe
            </Button>
          </CardContent>
        </Card>

        {/* Appearance */}
        <Card elevation="raised">
          <CardHeader>
            <div className="flex items-center gap-2">
              {theme === 'dark' ? <Moon className="h-5 w-5" /> : <Sun className="h-5 w-5" />}
              <CardTitle>Apparence</CardTitle>
            </div>
            <CardDescription>Personnalisez l'apparence de l'application</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between p-4 border rounded-lg">
              <div>
                <p className="font-medium">Thème</p>
                <p className="text-sm text-muted-foreground">
                  {theme === 'dark' ? 'Mode sombre activé' : 'Mode clair activé'}
                </p>
              </div>
              <div className="flex gap-2">
                <Button
                  variant={theme === 'light' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setTheme('light')}
                >
                  <Sun className="h-4 w-4 mr-1" />
                  Clair
                </Button>
                <Button
                  variant={theme === 'dark' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setTheme('dark')}
                >
                  <Moon className="h-4 w-4 mr-1" />
                  Sombre
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* API Keys */}
        <Card elevation="raised">
          <CardHeader>
            <div className="flex items-center gap-2">
              <Key className="h-5 w-5" />
              <CardTitle>Clés API Exchanges</CardTitle>
            </div>
            <CardDescription>Connectez vos exchanges pour synchroniser automatiquement vos positions</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="text-center py-8 text-muted-foreground">
              <p>Gérez vos connexions exchanges depuis la page dédiée.</p>
            </div>
            <Button onClick={() => window.location.href = '/exchanges'}>
              Gérer mes exchanges
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* MFA Dialog */}
      <Dialog open={mfaDialogOpen} onOpenChange={setMfaDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {user?.mfaEnabled ? 'Désactiver la MFA' : 'Configurer la MFA'}
            </DialogTitle>
            <DialogDescription>
              {user?.mfaEnabled
                ? 'Entrez votre code MFA pour désactiver la double authentification.'
                : 'Scannez le QR code avec votre application d\'authentification (Google Authenticator, Authy, etc.)'}
            </DialogDescription>
          </DialogHeader>

          {!user?.mfaEnabled && mfaQrCode && (
            <div className="flex flex-col items-center space-y-4">
              <img src={mfaQrCode} alt="QR Code MFA" className="w-48 h-48" />
              <div className="text-center">
                <p className="text-sm text-muted-foreground mb-1">Clé secrète (si vous ne pouvez pas scanner) :</p>
                <code className="text-xs bg-muted px-2 py-1 rounded font-mono break-all">{mfaSecret}</code>
              </div>
            </div>
          )}

          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="mfaCode">Code à 6 chiffres</Label>
              <Input
                id="mfaCode"
                placeholder="000000"
                maxLength={6}
                value={mfaCode}
                onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              />
            </div>
            <Button
              className="w-full"
              onClick={() => {
                if (user?.mfaEnabled) {
                  mfaDisableMutation.mutate()
                } else {
                  mfaVerifyMutation.mutate()
                }
              }}
              disabled={
                mfaCode.length !== 6 ||
                mfaVerifyMutation.isPending ||
                mfaDisableMutation.isPending
              }
            >
              {(mfaVerifyMutation.isPending || mfaDisableMutation.isPending) && (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              )}
              {user?.mfaEnabled ? 'Désactiver la MFA' : 'Vérifier et activer'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
