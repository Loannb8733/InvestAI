import { useState, useCallback } from 'react'

const STORAGE_KEY = 'investai-dashboard-layout'

// All available widget IDs
export const ALL_WIDGETS = [
  'metrics',
  'ia-summary',
  'munitions',
  'earn',
  'crowdfunding',
  'pnl',
  'risk',
  'roi-concentration',
  'indices',
  'charts',
  'currency-exposure',
  'allocation-transactions-alerts',
  'performers',
] as const

export type WidgetId = (typeof ALL_WIDGETS)[number]

export const WIDGET_LABELS: Record<WidgetId, string> = {
  'metrics': 'Patrimoine & KPIs',
  'ia-summary': 'Résumé IA',
  'munitions': 'Munitions Disponibles',
  'earn': 'Earn / Staking',
  'crowdfunding': 'Crowdfunding',
  'pnl': 'Répartition P&L',
  'risk': 'Métriques de risque',
  'roi-concentration': 'ROI & Concentration',
  'indices': 'Comparaison indices',
  'charts': 'Graphiques',
  'currency-exposure': 'Exposition Devises',
  'allocation-transactions-alerts': 'Allocation & Transactions',
  'performers': 'Top / Worst performers',
}

interface DashboardLayout {
  order: WidgetId[]
  hidden: WidgetId[]
}

function loadLayout(): DashboardLayout {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as DashboardLayout
      // Ensure all widgets are present (in case new ones are added)
      const existing = new Set([...parsed.order, ...parsed.hidden])
      for (const w of ALL_WIDGETS) {
        if (!existing.has(w)) parsed.order.push(w)
      }
      return parsed
    }
  } catch {
    // Ignore malformed localStorage data
  }
  return { order: [...ALL_WIDGETS], hidden: [] }
}

function saveLayout(layout: DashboardLayout) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(layout))
}

export function useDashboardLayout() {
  const [layout, setLayout] = useState<DashboardLayout>(loadLayout)

  const visibleWidgets = layout.order.filter((w) => !layout.hidden.includes(w))

  const toggleWidget = useCallback((id: WidgetId) => {
    setLayout((prev) => {
      const next = { ...prev }
      if (next.hidden.includes(id)) {
        next.hidden = next.hidden.filter((w) => w !== id)
      } else {
        next.hidden = [...next.hidden, id]
      }
      saveLayout(next)
      return next
    })
  }, [])

  const moveWidget = useCallback((fromIndex: number, toIndex: number) => {
    setLayout((prev) => {
      const visible = prev.order.filter((w) => !prev.hidden.includes(w))
      const item = visible[fromIndex]
      if (!item) return prev

      // Remove from visible list
      visible.splice(fromIndex, 1)
      // Insert at new position
      visible.splice(toIndex, 0, item)

      // Rebuild full order: visible items in new order, then hidden items
      const newOrder = [...visible, ...prev.hidden.filter((w) => !visible.includes(w))]
      const next = { ...prev, order: newOrder }
      saveLayout(next)
      return next
    })
  }, [])

  const resetLayout = useCallback(() => {
    const fresh: DashboardLayout = { order: [...ALL_WIDGETS], hidden: [] }
    saveLayout(fresh)
    setLayout(fresh)
  }, [])

  return {
    visibleWidgets,
    allWidgets: ALL_WIDGETS,
    hiddenWidgets: layout.hidden,
    toggleWidget,
    moveWidget,
    resetLayout,
  }
}
