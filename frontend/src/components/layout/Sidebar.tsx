import { useCallback } from 'react'
import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/authStore'
import {
  LayoutDashboard,
  Wallet,
  ArrowRightLeft,
  Link2,
  BarChart3,
  Bell,
  FileText,
  Settings,
  Users,
  TrendingUp,
  BookOpen,
  Calendar,
  Calculator,
  Lightbulb,
  Target,
  Brain,
  X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'

const navItems = [
  { icon: LayoutDashboard, label: 'Dashboard', path: '/' },
  { icon: Wallet, label: 'Portefeuille', path: '/portfolio' },
  { icon: ArrowRightLeft, label: 'Transactions', path: '/transactions' },
  { icon: Link2, label: 'Exchanges', path: '/exchanges' },
  { icon: BarChart3, label: 'Analyses', path: '/analytics' },
  { icon: TrendingUp, label: 'Projections', path: '/predictions' },
  { icon: Calculator, label: 'Simulations', path: '/simulations' },
  { icon: Lightbulb, label: 'Insights', path: '/insights' },
  { icon: Brain, label: 'Smart Insights', path: '/smart-insights' },
  { icon: Target, label: 'Objectifs', path: '/goals' },
  { icon: Bell, label: 'Alertes', path: '/alerts' },
  { icon: BookOpen, label: 'Journal', path: '/notes' },
  { icon: Calendar, label: 'Calendrier', path: '/calendar' },
  { icon: FileText, label: 'Rapports', path: '/reports' },
  { icon: Settings, label: 'Parametres', path: '/settings' },
]

const adminItems = [
  { icon: Users, label: 'Utilisateurs', path: '/admin' },
]

interface SidebarProps {
  isOpen?: boolean
  onClose?: () => void
}

export default function Sidebar({ isOpen = false, onClose }: SidebarProps) {
  const user = useAuthStore((state) => state.user)
  const isAdmin = user?.role === 'admin'

  const handleNavClick = useCallback(() => {
    // Close sidebar on mobile when a nav link is clicked
    onClose?.()
  }, [onClose])

  const sidebarContent = (
    <aside className="w-64 bg-card border-r border-border flex flex-col h-full">
      {/* Logo */}
      <div className="h-16 flex items-center justify-between px-6 border-b border-border">
        <div className="flex items-center">
          <TrendingUp className="h-8 w-8 text-primary mr-2" />
          <span className="text-xl font-bold">InvestAI</span>
        </div>
        {/* Close button visible only on mobile */}
        <Button
          variant="ghost"
          size="icon"
          className="lg:hidden"
          onClick={onClose}
          aria-label="Fermer le menu"
        >
          <X className="h-5 w-5" />
        </Button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto p-4 space-y-1" role="navigation" aria-label="Menu principal">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            onClick={handleNavClick}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
              )
            }
          >
            <item.icon className="h-5 w-5" />
            {item.label}
          </NavLink>
        ))}

        {/* Admin section */}
        {isAdmin && (
          <>
            <div className="pt-4 pb-2">
              <span className="px-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Administration
              </span>
            </div>
            {adminItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                onClick={handleNavClick}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-primary/10 text-primary'
                      : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                  )
                }
              >
                <item.icon className="h-5 w-5" />
                {item.label}
              </NavLink>
            ))}
          </>
        )}
      </nav>

      {/* User info */}
      <div className="p-4 border-t border-border">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-full bg-primary/20 flex items-center justify-center">
            <span className="text-sm font-medium text-primary">
              {user?.email?.charAt(0).toUpperCase()}
            </span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">{user?.email}</p>
            <p className="text-xs text-muted-foreground capitalize">{user?.role}</p>
          </div>
        </div>
      </div>
    </aside>
  )

  return (
    <>
      {/* Desktop sidebar: always visible, static */}
      <div className="hidden lg:flex lg:flex-shrink-0">
        {sidebarContent}
      </div>

      {/* Mobile sidebar: overlay with backdrop */}
      {/* Backdrop */}
      <div
        className={cn(
          'fixed inset-0 z-40 bg-black/50 transition-opacity lg:hidden',
          isOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'
        )}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Sliding panel */}
      <div
        className={cn(
          'fixed inset-y-0 left-0 z-50 transition-transform duration-300 ease-in-out lg:hidden',
          isOpen ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        {sidebarContent}
      </div>
    </>
  )
}
