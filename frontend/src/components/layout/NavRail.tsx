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
  Calendar,
  Target,
  Brain,
  FolderOpen,
  ShieldCheck,
  X,
  Bell,
  BookOpen,
  Lightbulb,
  Compass,
  Sparkles,
  type LucideIcon,
} from 'lucide-react'
import { Button } from '@/components/ui/button'

interface NavItem {
  icon: LucideIcon
  label: string
  path: string
}

interface NavGroup {
  label: string
  items: NavItem[]
}

const navGroups: NavGroup[] = [
  {
    label: 'Vue globale',
    items: [
      { icon: LayoutDashboard, label: 'Tableau de bord', path: '/' },
      { icon: Calendar, label: 'Calendrier', path: '/calendar' },
    ],
  },
  {
    label: 'Crypto',
    items: [
      { icon: Compass, label: "Vue d'ensemble", path: '/crypto' },
      { icon: Wallet, label: 'Portefeuille', path: '/portfolio' },
      { icon: Brain, label: 'Analyses IA', path: '/intelligence' },
    ],
  },
  {
    label: 'Crowdfunding',
    items: [
      { icon: FolderOpen, label: 'Mes Projets', path: '/crowdfunding' },
      { icon: ShieldCheck, label: 'Audit Lab', path: '/crowdfunding/audit-lab' },
    ],
  },
  {
    label: 'Outils',
    items: [
      { icon: Target, label: 'Objectifs', path: '/strategy' },
      { icon: FileText, label: 'Rapports', path: '/reports' },
      { icon: Bell, label: 'Alertes', path: '/alerts' },
      { icon: BookOpen, label: 'Notes', path: '/notes' },
      { icon: Lightbulb, label: 'Stratégies', path: '/strategies' },
    ],
  },
]

interface NavRailProps {
  isOpen?: boolean
  onClose?: () => void
}

export default function NavRail({ isOpen = false, onClose }: NavRailProps) {
  const user = useAuthStore((state) => state.user)
  const isAdmin = user?.role === 'admin'

  const handleNavClick = useCallback(() => {
    onClose?.()
  }, [onClose])

  // When `expanded` is true (mobile drawer) labels are always visible;
  // otherwise they fade in on hover of the rail (group).
  const renderBody = (expanded: boolean) => {
    const labelCls = cn(
      'overflow-hidden whitespace-nowrap transition-opacity duration-200',
      expanded ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
    )

    const renderLink = (item: NavItem) => (
      <NavLink
        key={item.path}
        to={item.path}
        end={item.path === '/'}
        onClick={handleNavClick}
        title={item.label}
        className={({ isActive }) =>
          cn(
            'relative flex h-11 items-center gap-3 rounded-xl px-3 text-sm transition-colors',
            isActive
              ? 'bg-primary/12 text-primary font-medium'
              : 'text-muted-foreground hover:bg-secondary/60 hover:text-foreground'
          )
        }
      >
        {({ isActive }) => (
          <>
            <span
              className={cn(
                'absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-primary transition-opacity',
                isActive ? 'opacity-100' : 'opacity-0'
              )}
              aria-hidden
            />
            <item.icon className="h-5 w-5 shrink-0" strokeWidth={1.75} />
            <span className={labelCls}>{item.label}</span>
          </>
        )}
      </NavLink>
    )

    return (
      <div className="flex h-full flex-col">
        {/* Logo */}
        <div className="flex h-16 items-center gap-3 px-4">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary/15 ring-1 ring-primary/30">
            <Sparkles className="h-5 w-5 text-primary" strokeWidth={2} />
          </div>
          <span className={cn(labelCls, 'text-lg font-semibold tracking-tight')}>InvestAI</span>
          <Button
            variant="ghost"
            size="icon"
            className="ml-auto lg:hidden"
            onClick={onClose}
            aria-label="Fermer le menu"
          >
            <X className="h-5 w-5" />
          </Button>
        </div>

        {/* Navigation */}
        <nav
          className="flex-1 space-y-4 overflow-y-auto overflow-x-hidden px-3 py-2"
          role="navigation"
          aria-label="Menu principal"
        >
          {navGroups.map((group) => (
            <div key={group.label} className="space-y-1">
              <div className="h-4 px-3">
                <span className={cn('eyebrow text-muted-foreground/70', labelCls)}>{group.label}</span>
              </div>
              {group.items.map(renderLink)}
            </div>
          ))}

          {isAdmin && (
            <div className="space-y-1">
              <div className="h-4 px-3">
                <span className={cn('eyebrow text-muted-foreground/70', labelCls)}>Administration</span>
              </div>
              {renderLink({ icon: Users, label: 'Utilisateurs', path: '/admin' })}
            </div>
          )}
        </nav>

        {/* Footer: settings + user */}
        <div className="space-y-1 border-t border-border/60 px-3 py-3">
          {renderLink({ icon: Settings, label: 'Paramètres', path: '/settings' })}
          <div className="flex h-12 items-center gap-3 rounded-xl px-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/15 ring-1 ring-primary/25">
              <span className="text-sm font-medium text-primary">
                {user?.email?.charAt(0).toUpperCase()}
              </span>
            </div>
            <div className={cn('min-w-0', labelCls)}>
              <p className="truncate text-sm font-medium">{user?.email}</p>
              <p className="truncate text-xs capitalize text-muted-foreground">{user?.role}</p>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <>
      {/* Desktop: spacer keeps content from sitting under the fixed rail */}
      <div className="hidden w-[76px] shrink-0 lg:block" aria-hidden />

      {/* Desktop rail — collapsed 76px, expands to 256px on hover (overlay) */}
      <aside className="group fixed inset-y-0 left-0 z-30 hidden w-[76px] overflow-hidden border-r border-border/60 bg-card/80 backdrop-blur-xl transition-[width] duration-300 ease-in-out hover:w-64 hover:shadow-[8px_0_40px_-12px_oklch(var(--background)/0.9)] lg:block">
        <div className="glow left-[-30%] top-[-10%] h-40 w-40 bg-[oklch(var(--primary))] opacity-30" aria-hidden />
        <div className="relative h-full">{renderBody(false)}</div>
      </aside>

      {/* Mobile: backdrop + drawer */}
      <div
        className={cn(
          'fixed inset-0 z-40 bg-black/60 backdrop-blur-sm transition-opacity lg:hidden',
          isOpen ? 'opacity-100' : 'pointer-events-none opacity-0'
        )}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 w-64 border-r border-border/60 bg-card transition-transform duration-300 ease-in-out lg:hidden',
          isOpen ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        <div className="h-full">{renderBody(true)}</div>
      </aside>
    </>
  )
}
