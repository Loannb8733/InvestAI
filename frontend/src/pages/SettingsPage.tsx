import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuthStore } from '@/stores/authStore'
import { useTheme } from '@/components/theme-provider'
import { authApi, profileApi } from '@/services/api'
import { useToast } from '@/hooks/use-toast'
import { Shield, User, Moon, Sun, Key, Loader2, Globe } from 'lucide-react'
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

export default function SettingsPage() {
  const user = useAuthStore((state) => state.user)
  const fetchCurrentUser = useAuthStore((state) => state.fetchCurrentUser)
  const { theme, setTheme } = useTheme()
  const { toast } = useToast()

  // Profile form state
  const [firstName, setFirstName] = useState(user?.firstName || '')
  const [lastName, setLastName] = useState(user?.lastName || '')
  const [preferredCurrency, setPreferredCurrency] = useState(user?.preferredCurrency || 'EUR')

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
    if (newPassword.length < 8) {
      toast({ title: 'Erreur', description: 'Le mot de passe doit contenir au moins 8 caractères.', variant: 'destructive' })
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
      <h1 className="text-3xl font-bold">Paramètres</h1>

      <div className="grid gap-6">
        {/* Profile */}
        <Card>
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
                Devise preferee
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
              <p className="text-xs text-muted-foreground">Tous les montants seront affiches dans cette devise</p>
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

        {/* Security */}
        <Card>
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
        <Card>
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
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Key className="h-5 w-5" />
              <CardTitle>Clés API Exchanges</CardTitle>
            </div>
            <CardDescription>Connectez vos exchanges pour synchroniser automatiquement vos positions</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="text-center py-8 text-muted-foreground">
              Aucune clé API configurée
            </div>
            <Button>
              Ajouter une clé API
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
