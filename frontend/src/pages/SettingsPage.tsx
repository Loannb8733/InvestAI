import { Key } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import AppearanceCard from '@/features/identity/components/AppearanceCard'
import InvestorProfileCard from '@/features/identity/components/InvestorProfileCard'
import ProfileCard from '@/features/identity/components/ProfileCard'
import SecurityCard from '@/features/identity/components/SecurityCard'

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-serif font-medium">Paramètres</h1>
      <div className="grid gap-6">
        <ProfileCard />
        <InvestorProfileCard />
        <SecurityCard />
        <AppearanceCard />
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
            <Button onClick={() => (window.location.href = '/exchanges')}>Gérer mes exchanges</Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
