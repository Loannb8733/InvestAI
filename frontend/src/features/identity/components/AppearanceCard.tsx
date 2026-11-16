import { Moon, Sun } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useTheme } from '@/components/theme-provider'

export default function AppearanceCard() {
  const { theme, setTheme } = useTheme()
  return (
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
            <p className="text-sm text-muted-foreground">{theme === 'dark' ? 'Mode sombre activé' : 'Mode clair activé'}</p>
          </div>
          <div className="flex gap-2">
            <Button variant={theme === 'light' ? 'default' : 'outline'} size="sm" onClick={() => setTheme('light')}>
              <Sun className="h-4 w-4 mr-1" />
              Clair
            </Button>
            <Button variant={theme === 'dark' ? 'default' : 'outline'} size="sm" onClick={() => setTheme('dark')}>
              <Moon className="h-4 w-4 mr-1" />
              Sombre
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
