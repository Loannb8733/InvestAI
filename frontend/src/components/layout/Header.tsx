import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useTheme } from '@/components/theme-provider'
import { Button } from '@/components/ui/button'
import { LogOut, Menu, Moon, Sun } from 'lucide-react'
import NotificationBell from './NotificationBell'
import Breadcrumb from './Breadcrumb'
import { useFilCourant } from './fil-ariane'

interface HeaderProps {
  onMenuClick?: () => void
}

export default function Header({ onMenuClick }: HeaderProps) {
  const fil = useFilCourant()
  const navigate = useNavigate()
  const logout = useAuthStore((state) => state.logout)
  const { theme, setTheme } = useTheme()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const toggleTheme = () => {
    setTheme(theme === 'dark' ? 'light' : 'dark')
  }

  return (
    <header className="h-16 border-b border-border bg-background flex items-center justify-between px-6">
      <div className="flex items-center gap-2">
        {/* Mobile hamburger menu */}
        <Button
          variant="ghost"
          size="icon"
          className="lg:hidden"
          onClick={onMenuClick}
          aria-label="Ouvrir le menu"
        >
          <Menu className="h-5 w-5" strokeWidth={1.5} />
        </Button>
        {/* Le repère de page, unique et au même endroit sur toutes les routes.
            Quinze pages n'en avaient aucun ; les cinq qui en portaient un le
            rendaient elles-mêmes, chacune à sa hauteur (UX-10). */}
        {fil ? <Breadcrumb items={fil} /> : null}
      </div>

      <div className="flex items-center gap-2">
        {/* Notifications */}
        <NotificationBell />

        {/* Theme toggle */}
        <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label={theme === 'dark' ? 'Passer au thème clair' : 'Passer au thème sombre'}>
          {theme === 'dark' ? (
            <Sun className="h-5 w-5" strokeWidth={1.5} />
          ) : (
            <Moon className="h-5 w-5" strokeWidth={1.5} />
          )}
        </Button>

        {/* Logout */}
        <Button variant="ghost" size="icon" onClick={handleLogout} aria-label="Se déconnecter">
          <LogOut className="h-5 w-5" strokeWidth={1.5} />
        </Button>
      </div>
    </header>
  )
}
