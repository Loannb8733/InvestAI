import { useEffect, useState } from 'react'
import { Globe, Loader2, User } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useAuthStore } from '@/stores/authStore'
import { useUpdateProfile } from '../hooks'

const CURRENCIES = [
  { value: 'EUR', label: 'EUR (€)' },
  { value: 'USD', label: 'USD ($)' },
  { value: 'CHF', label: 'CHF (CHF)' },
  { value: 'GBP', label: 'GBP (£)' },
]

export default function ProfileCard() {
  const user = useAuthStore((state) => state.user)
  const [firstName, setFirstName] = useState(user?.firstName || '')
  const [lastName, setLastName] = useState(user?.lastName || '')
  const [preferredCurrency, setPreferredCurrency] = useState(user?.preferredCurrency || 'EUR')
  const update = useUpdateProfile()

  useEffect(() => {
    if (user) {
      setFirstName(user.firstName || '')
      setLastName(user.lastName || '')
      setPreferredCurrency(user.preferredCurrency || 'EUR')
    }
  }, [user])

  return (
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
            <Input id="lastName" placeholder="Votre nom" value={lastName} onChange={(e) => setLastName(e.target.value)} />
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
                <SelectItem key={c.value} value={c.value}>
                  {c.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">Tous les montants seront affichés dans cette devise</p>
        </div>
        <Button
          onClick={() =>
            update.mutate({ first_name: firstName, last_name: lastName, preferred_currency: preferredCurrency })
          }
          disabled={update.isPending}
        >
          {update.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          Enregistrer les modifications
        </Button>
      </CardContent>
    </Card>
  )
}
