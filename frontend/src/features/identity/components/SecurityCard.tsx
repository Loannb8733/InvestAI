import { useState } from 'react'
import { Loader2, Shield } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useToast } from '@/hooks/use-toast'
import { useAuthStore } from '@/stores/authStore'
import { useChangePassword, useMfaSetup } from '../hooks'
import type { MfaSetup } from '../types'
import MfaDialog from './MfaDialog'

function PasswordField({ id, label, value, onChange }: { id: string; label: string; value: string; onChange: (value: string) => void }) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} type="password" placeholder="••••••••" value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  )
}

export default function SecurityCard() {
  const { toast } = useToast()
  const mfaEnabled = useAuthStore((state) => state.user?.mfaEnabled ?? false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [setup, setSetup] = useState<MfaSetup | null>(null)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  const mfaSetup = useMfaSetup((data) => {
    setSetup(data)
    setDialogOpen(true)
  })
  const changePassword = useChangePassword(() => {
    setCurrentPassword('')
    setNewPassword('')
    setConfirmPassword('')
  })

  const submitPassword = () => {
    if (newPassword !== confirmPassword) {
      toast({ title: 'Erreur', description: 'Les mots de passe ne correspondent pas.', variant: 'destructive' })
      return
    }
    if (newPassword.length < 10 || !/[A-Z]/.test(newPassword) || !/\d/.test(newPassword)) {
      toast({ title: 'Erreur', description: 'Le mot de passe doit contenir au moins 10 caractères, une majuscule et un chiffre.', variant: 'destructive' })
      return
    }
    changePassword.mutate({ current_password: currentPassword, new_password: newPassword })
  }

  return (
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
              {mfaEnabled ? 'La MFA est activée sur votre compte' : 'Protégez votre compte avec une authentification supplémentaire'}
            </p>
          </div>
          <Button
            variant={mfaEnabled ? 'destructive' : 'default'}
            onClick={() => (mfaEnabled ? setDialogOpen(true) : mfaSetup.mutate())}
            disabled={mfaSetup.isPending}
          >
            {mfaSetup.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            {mfaEnabled ? 'Désactiver' : 'Activer'}
          </Button>
        </div>
        <PasswordField id="currentPassword" label="Mot de passe actuel" value={currentPassword} onChange={setCurrentPassword} />
        <div className="grid gap-4 md:grid-cols-2">
          <PasswordField id="newPassword" label="Nouveau mot de passe" value={newPassword} onChange={setNewPassword} />
          <PasswordField id="confirmPassword" label="Confirmer le mot de passe" value={confirmPassword} onChange={setConfirmPassword} />
        </div>
        <Button onClick={submitPassword} disabled={changePassword.isPending || !currentPassword || !newPassword}>
          {changePassword.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          Changer le mot de passe
        </Button>
      </CardContent>
      <MfaDialog open={dialogOpen} enabled={mfaEnabled} setup={setup} onOpenChange={setDialogOpen} />
    </Card>
  )
}
