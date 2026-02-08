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
} from 'lucide-react'

const navItems = [
  { icon: LayoutDashboard, label: 'Dashboard', path: '/' },
  { icon: Wallet, label: 'Portefeuille', path: '/portfolio' },
  { icon: ArrowRightLeft, label: 'Transactions', path: '/transactions' },
  { icon: Link2, label: 'Exchanges', path: '/exchanges' },
  { icon: BarChart3, label: 'Analyses', path: '/analytics' },
  { icon: TrendingUp, label: 'Predictions', path: '/predictions' },
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

export default function Sidebar() {
  const user = useAuthStore((state) => state.user)
  const isAdmin = user?.role === 'admin'

  return (
    <aside className="w-64 bg-card border-r border-border flex flex-col">
      {/* Logo */}
      <div className="h-16 flex items-center px-6 border-b border-border">
        <TrendingUp className="h-8 w-8 text-primary mr-2" />
        <span className="text-xl font-bold">InvestAI</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4 space-y-1">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
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
}
