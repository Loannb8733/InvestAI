import type { LucideIcon } from 'lucide-react'
import {
  Bell,
  BookOpen,
  Brain,
  Calendar,
  Compass,
  FileText,
  FolderOpen,
  LayoutDashboard,
  Lightbulb,
  ShieldCheck,
  Target,
  Wallet,
} from 'lucide-react'

export interface NavItem {
  icon: LucideIcon
  label: string
  path: string
}

export interface NavGroup {
  label: string
  items: NavItem[]
}

export const navGroups: NavGroup[] = [
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
