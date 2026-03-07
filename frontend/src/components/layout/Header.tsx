import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useTheme } from '@/components/theme-provider'
import { Button } from '@/components/ui/button'
import { LogOut, Menu, Moon, Sun } from 'lucide-react'
import NotificationBell from './NotificationBell'

interface HeaderProps {
  onMenuClick?: () => void
}

export default function Header({ onMenuClick }: HeaderProps) {
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
    <header className="h-16 border-b border-white/[0.06] bg-background/80 backdrop-blur-md flex items-center justify-between px-6">
      <div className="flex items-center gap-2">
        {/* Mobile hamburger menu */}
        <Button
          variant="ghost"
          size="icon"
          className="lg:hidden"
          onClick={onMenuClick}
          aria-label="Ouvrir le menu"
        >
          <Menu className="h-5 w-5" />
        </Button>
        {/* Breadcrumb or page title could go here */}
      </div>

      <div className="flex items-center gap-2">
        {/* Notifications */}
        <NotificationBell />

        {/* Theme toggle */}
        <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label={theme === 'dark' ? 'Passer au thème clair' : 'Passer au thème sombre'}>
          {theme === 'dark' ? (
            <Sun className="h-5 w-5" />
          ) : (
            <Moon className="h-5 w-5" />
          )}
        </Button>

        {/* Logout */}
        <Button variant="ghost" size="icon" onClick={handleLogout} aria-label="Se déconnecter">
          <LogOut className="h-5 w-5" />
        </Button>
      </div>
    </header>
  )
}
