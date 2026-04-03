import { useCallback } from 'react'
import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/authStore'
import {
  LayoutDashboard,
  Wallet,
  FileText,
  Settings,
  Users,
  TrendingUp,
  Calendar,
  Target,
  Brain,
  FolderOpen,
  ShieldCheck,
  X,
  type LucideIcon,
} from 'lucide-react'
import { Button } from '@/components/ui/button'

interface NavItem {
  icon: LucideIcon
  label: string
  path: string
}

interface NavSection {
  label: string
  items: NavItem[]
}

const navSections: NavSection[] = [
  {
    label: 'VUE GLOBALE',
    items: [
      { icon: LayoutDashboard, label: 'Tableau de bord', path: '/' },
      { icon: Calendar, label: 'Calendrier', path: '/calendar' },
    ],
  },
  {
    label: 'UNIVERS CRYPTO',
    items: [
      { icon: LayoutDashboard, label: 'Vue d\'ensemble', path: '/crypto' },
      { icon: Wallet, label: 'Portefeuille', path: '/portfolio' },
      { icon: Brain, label: 'Analyses IA', path: '/intelligence' },
    ],
  },
  {
    label: 'CROWDFUNDING',
    items: [
      { icon: FolderOpen, label: 'Mes Projets', path: '/crowdfunding' },
      { icon: ShieldCheck, label: 'Audit Lab', path: '/crowdfunding/audit-lab' },
    ],
  },
  {
    label: 'OUTILS',
    items: [
      { icon: Target, label: 'Objectifs', path: '/strategy' },
      { icon: FileText, label: 'Rapports', path: '/reports' },
    ],
  },
]

const bottomItems: NavItem[] = [
  { icon: Settings, label: 'Parametres', path: '/settings' },
]

const adminItems: NavItem[] = [
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
    onClose?.()
  }, [onClose])

  const renderNavLink = (item: NavItem) => (
    <NavLink
      key={item.path}
      to={item.path}
      end={item.path === '/'}
      onClick={handleNavClick}
      className={({ isActive }) =>
        cn(
          'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
          isActive
            ? 'bg-indigo-500/10 text-indigo-400'
            : 'text-muted-foreground hover:bg-white/[0.05] hover:text-foreground'
        )
      }
    >
      <item.icon className="h-5 w-5" />
      {item.label}
    </NavLink>
  )

  const sidebarContent = (
    <aside className="w-64 bg-white/[0.02] border-r border-white/[0.06] backdrop-blur-xl flex flex-col h-full">
      {/* Logo */}
      <div className="h-16 flex items-center justify-between px-6 border-b border-white/[0.06]">
        <div className="flex items-center">
          <TrendingUp className="h-8 w-8 text-indigo-400 mr-2 drop-shadow-[0_0_8px_rgba(99,102,241,0.5)]" />
          <span className="text-xl font-bold">InvestAI</span>
        </div>
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

      {/* Navigation — sectioned */}
      <nav className="flex-1 overflow-y-auto p-4 space-y-1" role="navigation" aria-label="Menu principal">
        {navSections.map((section, idx) => (
          <div key={section.label}>
            <div className={cn('pb-2', idx === 0 ? 'pt-0' : 'pt-4')}>
              <span className="px-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                {section.label}
              </span>
            </div>
            {section.items.map(renderNavLink)}
          </div>
        ))}

        {/* Admin section */}
        {isAdmin && (
          <div>
            <div className="pt-4 pb-2">
              <span className="px-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Administration
              </span>
            </div>
            {adminItems.map(renderNavLink)}
          </div>
        )}
      </nav>

      {/* Bottom items (Settings) */}
      <div className="px-4 pb-2 space-y-1">
        {bottomItems.map(renderNavLink)}
      </div>

      {/* User info */}
      <div className="p-4 border-t border-white/[0.06]">
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
      <div
        className={cn(
          'fixed inset-0 z-40 bg-black/50 transition-opacity lg:hidden',
          isOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'
        )}
        onClick={onClose}
        aria-hidden="true"
      />

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
