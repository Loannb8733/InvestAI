import { useState, useMemo, useCallback, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { formatCurrency, formatDateTime } from '@/lib/utils'
import { invalidateAllFinancialData } from '@/lib/invalidate-queries'
import { queryKeys } from '@/lib/queryKeys'
import { transactionsApi, portfoliosApi } from '@/services/api'
import { useToast } from '@/hooks/use-toast'
import {
  Plus,
  ArrowUpRight,
  ArrowDownRight,
  Trash2,
  Loader2,
  Download,
  Upload,
  FileText,
  AlertTriangle,
  ArrowLeftRight,
  Pencil,
  Search,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  TrendingUp,
  TrendingDown,
  Coins,
  Receipt,
  X,
  SlidersHorizontal,
  FileSpreadsheet,
  MoreVertical,
  Shield,
} from 'lucide-react'
import { AssetIconCompact } from '@/components/ui/asset-icon'
import { isColdWallet } from '@/lib/platforms'
import StatCard from '@/components/ui/stat-card'
import SpotlightGroup from '@/components/ui/spotlight-group'
import EmptyState from '@/components/ui/empty-state'
import AddTransactionForm from '@/components/forms/AddTransactionForm'
import ImportCSVForm from '@/components/forms/ImportCSVForm'
import EditTransactionForm from '@/components/forms/EditTransactionForm'

import type { TransactionWithAssetInfo, PortfolioSummary } from '@/types'

// ============== Interfaces ==============

type Transaction = TransactionWithAssetInfo
type Portfolio = PortfolioSummary

interface CurrencyTotals {
  bought: number
  sold: number
  fees: number
  netFlow: number
}

interface TransactionStats {
  /** Totaux par devise (EUR, USD, ...) — jamais additionnés entre devises. */
  byCurrency: Record<string, CurrencyTotals>
  countByType: Record<string, number>
  /** Mouvements hors achats/ventes (transferts, rewards, airdrops, conversions). */
  excludedCount: number
}

/** Réponse serveur avec include_total=true : page filtrée + total filtré. */
interface TransactionsListPage {
  items: Transaction[]
  total: number
}

// ============== Constants ==============

const typeLabels: Record<string, string> = {
  buy: 'Achat',
  sell: 'Vente',
  transfer_in: 'Transfert entrant',
  transfer_out: 'Transfert sortant',
  staking_reward: 'Reward',
  airdrop: 'Airdrop',
  conversion_in: 'Conversion entrante',
  conversion_out: 'Conversion sortante',
  dividend: 'Dividende',
  interest: 'Intérêts',
  fee: 'Frais',
  staking: 'Staking',
  unstaking: 'Unstaking',
}

const typeColors: Record<string, string> = {
  buy: 'text-gain',
  sell: 'text-loss',
  transfer_in: 'text-accent',
  transfer_out: 'text-warning',
  staking_reward: 'text-warning',
  airdrop: 'text-accent',
  conversion_in: 'text-gain',
  conversion_out: 'text-warning',
  dividend: 'text-gain',
  interest: 'text-accent',
  fee: 'text-loss',
  staking: 'text-accent',
  unstaking: 'text-accent',
}

const typeOptions = [
  { value: 'all', label: 'Tous les types' },
  { value: 'buy', label: 'Achats' },
  { value: 'sell', label: 'Ventes' },
  { value: 'transfer_in', label: 'Transferts entrants' },
  { value: 'transfer_out', label: 'Transferts sortants' },
  { value: 'staking_reward', label: 'Rewards' },
  { value: 'airdrop', label: 'Airdrops' },
  { value: 'conversions', label: 'Conversions' },
  { value: 'dividend', label: 'Dividendes' },
  { value: 'interest', label: 'Intérêts' },
  { value: 'fee', label: 'Frais' },
  { value: 'staking', label: 'Staking' },
  { value: 'unstaking', label: 'Unstaking' },
]

const dateOptions = [
  { value: '0', label: 'Toutes les dates' },
  { value: '7', label: '7 derniers jours' },
  { value: '30', label: '30 derniers jours' },
  { value: '90', label: '90 derniers jours' },
  { value: 'ytd', label: 'Cette année' },
]

const conversionTypes = ['conversion_out', 'conversion_in']
const ITEMS_PER_PAGE = 20

type SortField = 'date' | 'type' | 'asset' | 'quantity' | 'price' | 'total' | 'fee'
type SortDirection = 'asc' | 'desc'

// ============== Helper Functions ==============

function formatQuantity(quantity: number): string {
  const q = Number(quantity)
  if (!q || q === 0) return '0'
  quantity = q
  const absQuantity = Math.abs(quantity)
  if (absQuantity >= 1000) {
    return quantity.toLocaleString('fr-FR', { maximumFractionDigits: 2 })
  } else if (absQuantity >= 1) {
    return quantity.toLocaleString('fr-FR', { maximumFractionDigits: 4 })
  } else if (absQuantity >= 0.0001) {
    return quantity.toLocaleString('fr-FR', { maximumFractionDigits: 6 })
  } else {
    return quantity.toLocaleString('fr-FR', { maximumSignificantDigits: 4 })
  }
}

function getDateRangeStart(value: string): Date | null {
  if (value === '0') return null
  if (value === 'ytd') {
    const now = new Date()
    return new Date(now.getFullYear(), 0, 1)  // January 1st of current year
  }
  const days = parseInt(value)
  if (isNaN(days) || days === 0) return null
  const date = new Date()
  date.setDate(date.getDate() - days)
  date.setHours(0, 0, 0, 0)
  return date
}

function generateCSV(transactions: Transaction[]): string {
  // Use backend-compatible format: machine-readable types, ISO dates, period decimals
  const headers = ['symbol', 'type', 'quantity', 'price', 'fee', 'date', 'notes']

  const rows = transactions.map((tx) => [
    tx.asset_symbol,
    tx.transaction_type,
    tx.quantity.toString(),
    tx.price.toString(),
    (tx.fee || 0).toString(),
    new Date(tx.executed_at || tx.created_at).toISOString().replace('T', ' ').substring(0, 19),
    (tx.notes || '').replace(/;/g, ',').replace(/\n/g, ' '),
  ])

  const csvContent = [headers.join(';'), ...rows.map((row) => row.join(';'))].join('\n')
  return '\uFEFF' + csvContent // BOM for Excel compatibility
}

function downloadCSV(content: string, filename: string) {
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' })
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  window.URL.revokeObjectURL(url)
  document.body.removeChild(a)
}

// ============== Main Component ==============

export default function TransactionsPage() {
  const queryClient = useQueryClient()
  const { toast } = useToast()

  // Dialog states
  const [isAddOpen, setIsAddOpen] = useState(false)
  const [isImportOpen, setIsImportOpen] = useState(false)
  const [editTransaction, setEditTransaction] = useState<Transaction | null>(null)
  const [deleteTransaction, setDeleteTransaction] = useState<Transaction | null>(null)

  // Filter states
  const [selectedPortfolio, setSelectedPortfolio] = useState<string>('all')
  const [selectedAsset, setSelectedAsset] = useState<string>('all')
  const [selectedPlatform, setSelectedPlatform] = useState<string>('all')
  const [selectedType, setSelectedType] = useState<string>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [dateRange, setDateRange] = useState<string>('0')

  // Pagination states
  const [currentPage, setCurrentPage] = useState(1)
  const [txSkip, setTxSkip] = useState(0)
  const TX_PAGE_SIZE = 200

  // Sorting states
  const [sortField, setSortField] = useState<SortField>('date')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')

  // Selection states
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  // Export states
  const [isExportingAll, setIsExportingAll] = useState(false)

  // ============== Queries ==============

  const { data: portfolios } = useQuery<Portfolio[]>({
    queryKey: queryKeys.portfolios.list(),
    queryFn: portfoliosApi.list,
    staleTime: 60_000,
  })

  // Recherche débouncée (300 ms) : évite une requête serveur à chaque frappe
  const [debouncedSearch, setDebouncedSearch] = useState('')
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchQuery.trim()), 300)
    return () => clearTimeout(timer)
  }, [searchQuery])

  /** Date de début (YYYY-MM-DD, locale) dérivée du filtre de période, envoyée au serveur. */
  const dateFrom = useMemo(() => {
    const start = getDateRangeStart(dateRange)
    if (!start) return undefined
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${start.getFullYear()}-${pad(start.getMonth() + 1)}-${pad(start.getDate())}`
  }, [dateRange])

  /** Filtres appliqués côté SERVEUR — exhaustifs sur tout l'historique, pas seulement les pages chargées. */
  const serverFilters = useMemo(
    () => ({
      portfolio_id: selectedPortfolio !== 'all' ? selectedPortfolio : undefined,
      transaction_type: selectedType !== 'all' ? selectedType : undefined,
      exchange: selectedPlatform !== 'all' ? selectedPlatform : undefined,
      asset_symbol: selectedAsset !== 'all' ? selectedAsset : undefined,
      date_from: dateFrom,
      search: debouncedSearch || undefined,
    }),
    [selectedPortfolio, selectedType, selectedPlatform, selectedAsset, dateFrom, debouncedSearch]
  )

  const { data: transactionsPage, isLoading } = useQuery<TransactionsListPage>({
    queryKey: [
      ...queryKeys.transactions.list(selectedPortfolio !== 'all' ? selectedPortfolio : undefined),
      serverFilters,
      txSkip,
    ],
    queryFn: () =>
      transactionsApi.list({
        ...serverFilters,
        skip: txSkip,
        limit: TX_PAGE_SIZE,
        include_total: true,
      }) as Promise<TransactionsListPage>,
    placeholderData: keepPreviousData,
  })

  const [accumulatedTx, setAccumulatedTx] = useState<Transaction[]>([])
  useEffect(() => {
    if (transactionsPage) {
      if (txSkip === 0) {
        setAccumulatedTx(transactionsPage.items)
      } else {
        setAccumulatedTx((prev) => {
          const existingIds = new Set(prev.map((t) => t.id))
          return [...prev, ...transactionsPage.items.filter((t) => !existingIds.has(t.id))]
        })
      }
    }
  }, [transactionsPage, txSkip])

  const transactions = accumulatedTx
  /** Total SERVEUR des transactions correspondant aux filtres (tout l'historique). */
  const totalCount = transactionsPage?.total ?? transactions.length
  const hasMoreTransactions = transactions.length < totalCount

  // ============== Derived Data ==============

  const uniqueAssets = useMemo(() => {
    if (!transactions) return []
    const assets = new Map<string, { symbol: string; name: string | null; count: number }>()
    transactions.forEach((tx) => {
      if (tx.asset_symbol) {
        const existing = assets.get(tx.asset_symbol)
        if (existing) {
          existing.count++
        } else {
          assets.set(tx.asset_symbol, { symbol: tx.asset_symbol, name: tx.asset_name, count: 1 })
        }
      }
    })
    const list = Array.from(assets.values()).sort((a, b) => b.count - a.count)
    // Garde l'actif sélectionné dans la liste même s'il n'apparaît pas dans les lignes chargées
    if (selectedAsset !== 'all' && !assets.has(selectedAsset)) {
      list.push({ symbol: selectedAsset, name: null, count: 0 })
    }
    return list
  }, [transactions, selectedAsset])

  const uniquePlatforms = useMemo(() => {
    if (!transactions) return []
    const platforms = new Map<string, number>()
    transactions.forEach((tx) => {
      const platform = tx.exchange || 'Manuel'
      platforms.set(platform, (platforms.get(platform) || 0) + 1)
    })
    const list = Array.from(platforms.entries())
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count)
    // Garde la plateforme sélectionnée dans la liste même si absente des lignes chargées
    if (selectedPlatform !== 'all' && !platforms.has(selectedPlatform)) {
      list.push({ name: selectedPlatform, count: 0 })
    }
    return list
  }, [transactions, selectedPlatform])

  // Les filtres (type, plateforme, dates, recherche, actif, portefeuille) sont désormais
  // appliqués côté SERVEUR : les transactions chargées sont déjà filtrées et exhaustives.
  const filteredTransactions = transactions

  const sortedTransactions = useMemo(() => {
    const sorted = [...filteredTransactions]
    sorted.sort((a, b) => {
      let comparison = 0
      switch (sortField) {
        case 'date':
          comparison =
            new Date(a.executed_at || a.created_at).getTime() -
            new Date(b.executed_at || b.created_at).getTime()
          break
        case 'type':
          comparison = (typeLabels[a.transaction_type] || a.transaction_type).localeCompare(
            typeLabels[b.transaction_type] || b.transaction_type
          )
          break
        case 'asset':
          comparison = (a.asset_symbol || '').localeCompare(b.asset_symbol || '')
          break
        case 'quantity':
          comparison = a.quantity - b.quantity
          break
        case 'price':
          comparison = a.price - b.price
          break
        case 'total':
          comparison = a.quantity * a.price - b.quantity * b.price
          break
        case 'fee':
          comparison = (a.fee || 0) - (b.fee || 0)
          break
      }
      return sortDirection === 'asc' ? comparison : -comparison
    })
    return sorted
  }, [filteredTransactions, sortField, sortDirection])

  const stats = useMemo<TransactionStats>(() => {
    const byCurrency: Record<string, CurrencyTotals> = {}
    const countByType: Record<string, number> = {}
    // Mouvements qui gonflaient à tort achats/ventes : exclus des flux, comptés séparément.
    const excludedTypes = [
      'transfer_in',
      'transfer_out',
      'staking_reward',
      'airdrop',
      'conversion_in',
      'conversion_out',
    ]
    let excludedCount = 0

    filteredTransactions.forEach((tx) => {
      countByType[tx.transaction_type] = (countByType[tx.transaction_type] || 0) + 1
      const currency = tx.currency || 'EUR'
      const entry = (byCurrency[currency] ??= { bought: 0, sold: 0, fees: 0, netFlow: 0 })
      const total = (Number(tx.quantity) || 0) * (Number(tx.price) || 0)
      // Les frais sont réels sur tous les types de mouvements.
      entry.fees += Number(tx.fee) || 0
      if (tx.transaction_type === 'buy') {
        entry.bought += total
      } else if (tx.transaction_type === 'sell') {
        entry.sold += total
      } else if (excludedTypes.includes(tx.transaction_type)) {
        excludedCount++
      }
    })

    Object.values(byCurrency).forEach((entry) => {
      entry.netFlow = entry.bought - entry.sold
    })

    return { byCurrency, countByType, excludedCount }
  }, [filteredTransactions])

  const eurTotals: CurrencyTotals = stats.byCurrency['EUR'] ?? {
    bought: 0,
    sold: 0,
    fees: 0,
    netFlow: 0,
  }

  const otherCurrencies = useMemo(
    () => Object.keys(stats.byCurrency).filter((c) => c !== 'EUR').sort(),
    [stats.byCurrency]
  )

  /** Lignes secondaires « + 1 234,56 $US » pour les devises non-EUR (jamais converties). */
  const otherCurrencyLines = useCallback(
    (field: keyof CurrencyTotals): React.ReactNode[] =>
      otherCurrencies
        .filter((c) => stats.byCurrency[c][field] !== 0)
        .map((c) => {
          const amount = stats.byCurrency[c][field]
          return (
            <span key={`${field}-${c}`} className="block">
              {amount >= 0 ? '+ ' : ''}
              {formatCurrency(amount, c)}
            </span>
          )
        }),
    [otherCurrencies, stats.byCurrency]
  )

  const excludedHint =
    stats.excludedCount > 0
      ? stats.excludedCount > 1
        ? `${stats.excludedCount} transferts/rewards exclus`
        : '1 transfert/reward exclu'
      : null

  /** Les StatCards sont calculées sur les lignes filtrées CHARGÉES : si le total
   * serveur dépasse le chargé, on le signale. */
  const partialLoadHint =
    totalCount > transactions.length ? `sur les ${transactions.length} chargées` : null

  const totalPages = Math.max(1, Math.ceil(sortedTransactions.length / ITEMS_PER_PAGE))

  // Reset to last valid page if current page exceeds total after deletion
  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(totalPages)
    }
  }, [currentPage, totalPages])
  const paginatedTransactions = useMemo(() => {
    const start = (currentPage - 1) * ITEMS_PER_PAGE
    return sortedTransactions.slice(start, start + ITEMS_PER_PAGE)
  }, [sortedTransactions, currentPage])

  useEffect(() => {
    setCurrentPage(1)
    setTxSkip(0)
    setSelectedIds(new Set())
  }, [selectedPortfolio, selectedAsset, selectedPlatform, selectedType, dateRange, debouncedSearch])

  // ============== Mutations ==============

  const deleteMutation = useMutation({
    mutationFn: transactionsApi.delete,
    onSuccess: () => {
      invalidateAllFinancialData(queryClient)
      toast({ title: 'Transaction supprimée' })
      setDeleteTransaction(null)
    },
    onError: () => {
      toast({ title: 'Erreur lors de la suppression', variant: 'destructive' })
    },
  })

  const deleteMultipleMutation = useMutation({
    mutationFn: async (ids: string[]) => {
      let deleted = 0
      const errors: string[] = []
      for (const id of ids) {
        try {
          await transactionsApi.delete(id)
          deleted++
        } catch {
          errors.push(id)
        }
      }
      return { deleted_count: deleted, errors }
    },
    onSuccess: (data) => {
      invalidateAllFinancialData(queryClient)
      if (data.errors.length > 0) {
        toast({ title: `${data.deleted_count} supprimées, ${data.errors.length} erreurs`, variant: 'destructive' })
      } else {
        toast({ title: `${data.deleted_count} transactions supprimées` })
      }
      setSelectedIds(new Set())
    },
    onError: () => {
      toast({ title: 'Erreur lors de la suppression', variant: 'destructive' })
    },
  })

  const deleteAllMutation = useMutation({
    mutationFn: () => transactionsApi.deleteAll(
      selectedPortfolio !== 'all' ? selectedPortfolio : undefined
    ),
    onSuccess: (data: { deleted_count: number }) => {
      invalidateAllFinancialData(queryClient)
      toast({ title: `${data.deleted_count} transactions supprimées` })
    },
    onError: () => {
      toast({ title: 'Erreur lors de la suppression', variant: 'destructive' })
    },
  })

  // ============== Handlers ==============

  /** Export SERVEUR : toutes les transactions, pas seulement les pages chargées côté client. */
  const handleExportAll = async () => {
    if (isExportingAll) return
    setIsExportingAll(true)
    try {
      const blob = await transactionsApi.exportCSV(
        selectedPortfolio !== 'all' ? selectedPortfolio : undefined
      )
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `transactions_all_${new Date().toISOString().split('T')[0]}.csv`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
      toast({
        title: 'Export complet téléchargé',
        description:
          selectedPortfolio !== 'all'
            ? 'Toutes les transactions du portefeuille ont été exportées.'
            : 'Toutes les transactions ont été exportées.',
      })
    } catch {
      toast({ title: "Erreur lors de l'export", variant: 'destructive' })
    } finally {
      setIsExportingAll(false)
    }
  }

  const handleExportFiltered = () => {
    if (filteredTransactions.length === 0) {
      toast({ title: 'Aucune transaction à exporter', variant: 'destructive' })
      return
    }
    const csv = generateCSV(filteredTransactions)
    downloadCSV(csv, `transactions_filtered_${new Date().toISOString().split('T')[0]}.csv`)
    toast({ title: `${filteredTransactions.length} transactions exportées` })
  }

  const handleExportSelected = () => {
    if (selectedIds.size === 0) {
      toast({ title: 'Aucune transaction sélectionnée', variant: 'destructive' })
      return
    }
    const selectedTransactions = sortedTransactions.filter((tx) => selectedIds.has(tx.id))
    const csv = generateCSV(selectedTransactions)
    downloadCSV(csv, `transactions_selected_${new Date().toISOString().split('T')[0]}.csv`)
    toast({ title: `${selectedTransactions.length} transactions exportées` })
  }

  const handleSort = useCallback(
    (field: SortField) => {
      if (sortField === field) {
        setSortDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'))
      } else {
        setSortField(field)
        setSortDirection('desc')
      }
    },
    [sortField]
  )

  const handleSelectAll = useCallback(() => {
    const currentPageIds = paginatedTransactions.map((tx) => tx.id)
    const allSelected = currentPageIds.length > 0 && currentPageIds.every((id) => selectedIds.has(id))
    setSelectedIds((prev) => {
      const newSet = new Set(prev)
      if (allSelected) {
        currentPageIds.forEach((id) => newSet.delete(id))
      } else {
        currentPageIds.forEach((id) => newSet.add(id))
      }
      return newSet
    })
  }, [paginatedTransactions, selectedIds])

  const handleSelectOne = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const newSet = new Set(prev)
      if (newSet.has(id)) {
        newSet.delete(id)
      } else {
        newSet.add(id)
      }
      return newSet
    })
  }, [])

  const clearFilters = () => {
    setSelectedAsset('all')
    setSelectedPlatform('all')
    setSelectedType('all')
    setDateRange('0')
    setSearchQuery('')
  }

  const hasActiveFilters =
    selectedAsset !== 'all' ||
    selectedPlatform !== 'all' ||
    selectedType !== 'all' ||
    dateRange !== '0' ||
    searchQuery !== ''

  const activeFilterCount = [
    selectedAsset !== 'all',
    selectedPlatform !== 'all',
    selectedType !== 'all',
    dateRange !== '0',
    searchQuery !== '',
  ].filter(Boolean).length

  const getTotal = (tx: Transaction) => tx.quantity * tx.price

  // ============== Render Helpers ==============

  const SortableHeader = ({
    field,
    children,
    title,
  }: {
    field: SortField
    children: React.ReactNode
    title?: string
  }) => (
    <th scope="col"
      title={title}
      className="text-center py-3 text-sm font-medium text-muted-foreground cursor-pointer hover:text-foreground transition-colors select-none"
      onClick={() => handleSort(field)}
    >
      <div className="flex items-center justify-center gap-1">
        {children}
        {sortField === field ? (
          sortDirection === 'asc' ? (
            <ArrowUp className="h-3 w-3" />
          ) : (
            <ArrowDown className="h-3 w-3" />
          )
        ) : (
          <ArrowUpDown className="h-3 w-3 opacity-30" />
        )}
      </div>
    </th>
  )

  // ============== Loading State ==============

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  // ============== Main Render ==============

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-serif font-medium">Transactions</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Chaque mouvement qui a façonné ton patrimoine.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {/* Export Dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline">
                <Download className="h-4 w-4 mr-2" />
                Exporter
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={handleExportAll} disabled={isExportingAll}>
                {isExportingAll ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <FileSpreadsheet className="h-4 w-4 mr-2" />
                )}
                Tout exporter (serveur)
              </DropdownMenuItem>
              {hasActiveFilters && (
                <DropdownMenuItem onClick={handleExportFiltered}>
                  <SlidersHorizontal className="h-4 w-4 mr-2" />
                  Exporter filtrés ({filteredTransactions.length})
                </DropdownMenuItem>
              )}
              {selectedIds.size > 0 && (
                <DropdownMenuItem onClick={handleExportSelected}>
                  <Checkbox className="h-4 w-4 mr-2" checked />
                  Exporter sélection ({selectedIds.size})
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>

          <Dialog open={isImportOpen} onOpenChange={setIsImportOpen}>
            <DialogTrigger asChild>
              <Button variant="outline">
                <Upload className="h-4 w-4 mr-2" />
                <span className="hidden sm:inline">Importer</span>
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Importer des transactions</DialogTitle>
                <DialogDescription>Importez vos transactions depuis un fichier CSV</DialogDescription>
              </DialogHeader>
              <ImportCSVForm
                portfolioId={selectedPortfolio !== 'all' ? selectedPortfolio : undefined}
                onSuccess={() => {
                  setIsImportOpen(false)
                  queryClient.invalidateQueries({ queryKey: queryKeys.transactions.all })
                }}
              />
            </DialogContent>
          </Dialog>

          <Dialog open={isAddOpen} onOpenChange={setIsAddOpen}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="h-4 w-4 mr-2" />
                <span className="hidden sm:inline">Nouvelle</span>
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Ajouter une transaction</DialogTitle>
                <DialogDescription>Enregistrez une nouvelle transaction</DialogDescription>
              </DialogHeader>
              <AddTransactionForm
                onSuccess={() => {
                  setIsAddOpen(false)
                  queryClient.invalidateQueries({ queryKey: queryKeys.transactions.all })
                  queryClient.invalidateQueries({ queryKey: queryKeys.assets.all })
                }}
              />
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Statistics Cards */}
      {transactions && transactions.length > 0 && (
        <SpotlightGroup className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            className="spot-card"
            label={`Total achats${hasActiveFilters ? ' (filtrés)' : ''}`}
            tooltip="Achats (BUY) uniquement — transferts, conversions et récompenses exclus."
            icon={TrendingUp}
            value={eurTotals.bought}
            format={formatCurrency}
            hint={
              otherCurrencyLines('bought').length > 0 || excludedHint || partialLoadHint ? (
                <>
                  {otherCurrencyLines('bought')}
                  {excludedHint && <span className="block">{excludedHint}</span>}
                  {partialLoadHint && <span className="block">{partialLoadHint}</span>}
                </>
              ) : undefined
            }
          />
          <StatCard
            className="spot-card"
            label={`Total ventes${hasActiveFilters ? ' (filtrés)' : ''}`}
            tooltip="Ventes (SELL) uniquement — transferts, conversions et récompenses exclus."
            icon={TrendingDown}
            value={eurTotals.sold}
            format={formatCurrency}
            hint={
              otherCurrencyLines('sold').length > 0 || excludedHint || partialLoadHint ? (
                <>
                  {otherCurrencyLines('sold')}
                  {excludedHint && <span className="block">{excludedHint}</span>}
                  {partialLoadHint && <span className="block">{partialLoadHint}</span>}
                </>
              ) : undefined
            }
          />
          <StatCard
            className="spot-card"
            label={`Total frais${hasActiveFilters ? ' (filtrés)' : ''}`}
            tooltip="Frais de tous les types de mouvements, cumulés par devise."
            icon={Receipt}
            value={eurTotals.fees}
            format={formatCurrency}
            hint={
              otherCurrencyLines('fees').length > 0 || partialLoadHint ? (
                <>
                  {otherCurrencyLines('fees')}
                  {partialLoadHint && <span className="block">{partialLoadHint}</span>}
                </>
              ) : undefined
            }
          />
          <StatCard
            className="spot-card"
            label={`Flux net investi${hasActiveFilters ? ' (filtrés)' : ''}`}
            icon={Coins}
            value={eurTotals.netFlow}
            format={formatCurrency}
            hint={
              <>
                <span className="block">hors transferts internes, conversions et récompenses</span>
                {otherCurrencyLines('netFlow')}
                {partialLoadHint && <span className="block">{partialLoadHint}</span>}
              </>
            }
          />
        </SpotlightGroup>
      )}

      {/* Main Content Card */}
      <Card elevation="raised">
        <CardHeader className="pb-4">
          <div className="flex flex-col gap-4">
            {/* Title and Search Row */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <CardTitle className="flex items-center gap-2">
                Historique
                <Badge variant="secondary">{filteredTransactions.length}</Badge>
              </CardTitle>

              <div className="relative w-full sm:w-72">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Rechercher..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9 pr-9"
                />
                {searchQuery && (
                  <button
                    onClick={() => setSearchQuery('')}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
              </div>
            </div>

            {/* Compact Filters Row */}
            <div className="flex flex-wrap items-center gap-2">
              {/* Portfolio Filter */}
              <Select value={selectedPortfolio} onValueChange={setSelectedPortfolio}>
                <SelectTrigger className="w-40 h-9">
                  <SelectValue placeholder="Portefeuille" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Tous les portefeuilles</SelectItem>
                  {portfolios?.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {/* Date Filter */}
              <Select value={dateRange} onValueChange={setDateRange}>
                <SelectTrigger className="w-36 h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {dateOptions.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {/* Type Filter */}
              <Select value={selectedType} onValueChange={setSelectedType}>
                <SelectTrigger className="w-36 h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {typeOptions.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {/* Asset Filter */}
              {uniqueAssets.length > 0 && (
                <Select value={selectedAsset} onValueChange={setSelectedAsset}>
                  <SelectTrigger className="w-32 h-9">
                    <SelectValue placeholder="Actif" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Tous les actifs</SelectItem>
                    {uniqueAssets.map((asset) => (
                      <SelectItem key={asset.symbol} value={asset.symbol}>
                        {asset.symbol} ({asset.count})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}

              {/* Platform Filter */}
              {uniquePlatforms.length > 1 && (
                <Select value={selectedPlatform} onValueChange={setSelectedPlatform}>
                  <SelectTrigger className="w-32 h-9">
                    <SelectValue placeholder="Plateforme" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Toutes</SelectItem>
                    {uniquePlatforms.map((p) => (
                      <SelectItem key={p.name} value={p.name}>
                        {p.name} ({p.count})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}

              {/* Clear Filters */}
              {hasActiveFilters && (
                <Button variant="ghost" size="sm" onClick={clearFilters} className="h-9 px-2">
                  <X className="h-4 w-4 mr-1" />
                  Effacer ({activeFilterCount})
                </Button>
              )}
            </div>

            {/* Active Filter Badges */}
            {hasActiveFilters && (
              <div className="flex flex-wrap gap-2">
                {dateRange !== '0' && (
                  <Badge variant="secondary" className="gap-1">
                    {dateOptions.find((d) => d.value === dateRange)?.label}
                    <X className="h-3 w-3 cursor-pointer" onClick={() => setDateRange('0')} />
                  </Badge>
                )}
                {selectedType !== 'all' && (
                  <Badge variant="secondary" className="gap-1">
                    {typeOptions.find((t) => t.value === selectedType)?.label}
                    <X className="h-3 w-3 cursor-pointer" onClick={() => setSelectedType('all')} />
                  </Badge>
                )}
                {selectedAsset !== 'all' && (
                  <Badge variant="secondary" className="gap-1">
                    {selectedAsset}
                    <X className="h-3 w-3 cursor-pointer" onClick={() => setSelectedAsset('all')} />
                  </Badge>
                )}
                {selectedPlatform !== 'all' && (
                  <Badge variant="secondary" className="gap-1">
                    {selectedPlatform}
                    <X className="h-3 w-3 cursor-pointer" onClick={() => setSelectedPlatform('all')} />
                  </Badge>
                )}
                {searchQuery && (
                  <Badge variant="secondary" className="gap-1">
                    "{searchQuery}"
                    <X className="h-3 w-3 cursor-pointer" onClick={() => setSearchQuery('')} />
                  </Badge>
                )}
              </div>
            )}

            {/* Selection Actions */}
            {selectedIds.size > 0 && (
              <div className="flex items-center gap-4 p-3 bg-primary/10 rounded-lg">
                <span className="text-sm font-medium">
                  {selectedIds.size} sélectionnée{selectedIds.size > 1 ? 's' : ''}
                </span>
                <Button variant="outline" size="sm" onClick={handleExportSelected}>
                  <Download className="h-4 w-4 mr-1" />
                  Exporter
                </Button>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button variant="destructive" size="sm">
                      <Trash2 className="h-4 w-4 mr-1" />
                      Supprimer
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle className="flex items-center gap-2">
                        <AlertTriangle className="h-5 w-5 text-destructive" />
                        Supprimer {selectedIds.size} transaction{selectedIds.size > 1 ? 's' : ''} ?
                      </AlertDialogTitle>
                      <AlertDialogDescription>
                        Cette action est irréversible. Les transactions sélectionnées seront définitivement
                        supprimées.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Annuler</AlertDialogCancel>
                      <AlertDialogAction
                        onClick={() => deleteMultipleMutation.mutate(Array.from(selectedIds))}
                        className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                        disabled={deleteMultipleMutation.isPending}
                      >
                        {deleteMultipleMutation.isPending ? (
                          <>
                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                            Suppression...
                          </>
                        ) : (
                          'Supprimer'
                        )}
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
                <Button variant="ghost" size="sm" onClick={() => setSelectedIds(new Set())}>
                  Désélectionner
                </Button>
              </div>
            )}
          </div>
        </CardHeader>

        <CardContent>
          {/* Avertissement : les filtres ne portent que sur les pages déjà chargées */}
          {hasActiveFilters && hasMoreTransactions && (
            <div className="flex items-start gap-2 mb-4 px-3 py-2 rounded-md border border-warning/30 bg-warning/10 text-sm text-warning">
              <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
              <span>
                Filtres appliqués sur les {transactions.length} transactions chargées — les
                suivantes n'ont pas été parcourues.{' '}
                <button
                  type="button"
                  className="underline underline-offset-2 hover:opacity-80 font-medium"
                  onClick={() => setTxSkip((s) => s + TX_PAGE_SIZE)}
                >
                  Charger plus
                </button>{' '}
                pour une vue exhaustive.
              </span>
            </div>
          )}
          {paginatedTransactions.length > 0 ? (
            <>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b">
                      <th scope="col" className="text-center py-3 w-10">
                        <Checkbox
                          checked={
                            paginatedTransactions.length > 0 &&
                            paginatedTransactions.every((tx) => selectedIds.has(tx.id))
                          }
                          onCheckedChange={handleSelectAll}
                        />
                      </th>
                      <SortableHeader field="date">Date</SortableHeader>
                      <SortableHeader field="type">Type</SortableHeader>
                      <SortableHeader field="asset">Actif</SortableHeader>
                      <th scope="col" className="text-center py-3 text-sm font-medium text-muted-foreground">Plateforme</th>
                      <SortableHeader field="quantity">Quantité</SortableHeader>
                      <SortableHeader field="price">Prix</SortableHeader>
                      <SortableHeader field="total" title="Hors frais">Total</SortableHeader>
                      <SortableHeader field="fee">Frais</SortableHeader>
                      <th scope="col" className="text-center py-3 text-sm font-medium text-muted-foreground w-20">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {paginatedTransactions.map((tx) => (
                      <tr key={tx.id} className="border-b last:border-0 hover:bg-muted/50">
                        <td className="text-center py-3">
                          <Checkbox checked={selectedIds.has(tx.id)} onCheckedChange={() => handleSelectOne(tx.id)} />
                        </td>
                        <td className="py-3 text-sm text-center whitespace-nowrap">
                          {formatDateTime(tx.executed_at || tx.created_at)}
                        </td>
                        <td className="py-3 text-center">
                          <div className="flex items-center justify-center gap-1">
                            {conversionTypes.includes(tx.transaction_type) ? (
                              <ArrowLeftRight
                                className={`h-4 w-4 ${typeColors[tx.transaction_type] || 'text-gray-500'}`}
                              />
                            ) : [
                                'buy',
                                'transfer_in',
                                'staking_reward',
                                'airdrop',
                                'unstaking',
                              ].includes(tx.transaction_type) ? (
                              <ArrowDownRight
                                className={`h-4 w-4 ${typeColors[tx.transaction_type] || 'text-gray-500'}`}
                              />
                            ) : (
                              <ArrowUpRight
                                className={`h-4 w-4 ${typeColors[tx.transaction_type] || 'text-gray-500'}`}
                              />
                            )}
                            <span
                              className={`text-sm font-medium ${typeColors[tx.transaction_type] || 'text-gray-500'}`}
                            >
                              {typeLabels[tx.transaction_type] || tx.transaction_type}
                            </span>
                          </div>
                        </td>
                        <td className="py-3 text-center">
                          <div className="flex items-center justify-center gap-2">
                            <AssetIconCompact
                              symbol={tx.asset_symbol || '?'}
                              name={tx.asset_name || undefined}
                              assetType={tx.asset_type}
                              size={28}
                            />
                          </div>
                        </td>
                        <td className="py-3 text-center">
                          <span className={`text-xs px-2 py-1 rounded inline-flex items-center gap-1 ${
                            tx.exchange && isColdWallet(tx.exchange)
                              ? 'bg-accent/10 text-accent'
                              : 'bg-muted'
                          }`}>
                            {tx.exchange && isColdWallet(tx.exchange) && <Shield className="h-3 w-3" />}
                            {tx.exchange || 'Manuel'}
                          </span>
                        </td>
                        <td className="text-center py-3 font-mono text-sm">{formatQuantity(tx.quantity)}</td>
                        <td className="text-center py-3 text-sm">{formatCurrency(tx.price, tx.currency)}</td>
                        <td className="text-center py-3 font-medium text-sm">
                          {formatCurrency(getTotal(tx), tx.currency)}
                        </td>
                        <td className="text-center py-3 text-muted-foreground text-sm">
                          {tx.fee && Number(tx.fee) > 0 ? formatCurrency(Number(tx.fee), tx.currency) : '-'}
                        </td>
                        <td className="text-center py-3">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="icon" className="h-8 w-8">
                                <MoreVertical className="h-4 w-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem onClick={() => setEditTransaction(tx)}>
                                <Pencil className="h-4 w-4 mr-2" />
                                Modifier
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                onClick={() => setDeleteTransaction(tx)}
                                className="text-destructive focus:text-destructive"
                              >
                                <Trash2 className="h-4 w-4 mr-2" />
                                Supprimer
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-between mt-4 pt-4 border-t">
                  <div className="text-sm text-muted-foreground">
                    {(currentPage - 1) * ITEMS_PER_PAGE + 1}-
                    {Math.min(currentPage * ITEMS_PER_PAGE, sortedTransactions.length)} sur{' '}
                    {sortedTransactions.length}
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="outline"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => setCurrentPage(1)}
                      disabled={currentPage === 1}
                    >
                      <ChevronsLeft className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="outline"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
                      disabled={currentPage === 1}
                    >
                      <ChevronLeft className="h-4 w-4" />
                    </Button>

                    <div className="flex items-center gap-1 mx-2">
                      {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                        let pageNum: number
                        if (totalPages <= 5) {
                          pageNum = i + 1
                        } else if (currentPage <= 3) {
                          pageNum = i + 1
                        } else if (currentPage >= totalPages - 2) {
                          pageNum = totalPages - 4 + i
                        } else {
                          pageNum = currentPage - 2 + i
                        }
                        return (
                          <Button
                            key={pageNum}
                            variant={currentPage === pageNum ? 'default' : 'outline'}
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => setCurrentPage(pageNum)}
                          >
                            {pageNum}
                          </Button>
                        )
                      })}
                    </div>

                    <Button
                      variant="outline"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => setCurrentPage((prev) => Math.min(totalPages, prev + 1))}
                      disabled={currentPage === totalPages}
                    >
                      <ChevronRight className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="outline"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => setCurrentPage(totalPages)}
                      disabled={currentPage === totalPages}
                    >
                      <ChevronsRight className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              )}
              {hasMoreTransactions && (
                <div className="flex justify-center mt-4">
                  <Button variant="outline" onClick={() => setTxSkip((s) => s + TX_PAGE_SIZE)}>
                    Charger plus de transactions
                  </Button>
                </div>
              )}
            </>
          ) : (
            <EmptyState
              variant={hasActiveFilters ? 'search' : 'empty'}
              icon={FileText}
              title={hasActiveFilters ? 'Aucun résultat' : 'Aucune transaction'}
              description={
                hasActiveFilters
                  ? 'Essayez de modifier vos filtres pour trouver des transactions.'
                  : 'Ajoutez votre première transaction ou importez un fichier CSV.'
              }
              action={
                hasActiveFilters ? (
                  <Button variant="outline" onClick={clearFilters}>
                    <X className="h-4 w-4 mr-2" />
                    Effacer les filtres
                  </Button>
                ) : (
                  <Button onClick={() => setIsAddOpen(true)}>
                    <Plus className="h-4 w-4 mr-2" />
                    Ajouter une transaction
                  </Button>
                )
              }
            />
          )}
        </CardContent>
      </Card>

      {/* Danger Zone */}
      {transactions && transactions.length > 0 && (
        <Card elevation="raised" className="border-destructive/50">
          <CardHeader className="pb-3">
            <CardTitle className="text-destructive flex items-center gap-2 text-base">
              <AlertTriangle className="h-4 w-4" />
              Zone dangereuse
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium text-sm">Supprimer toutes les transactions</p>
                <p className="text-xs text-muted-foreground">
                  Supprime {transactions.length} transactions et remet les quantités à zéro.
                </p>
              </div>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="destructive" size="sm">
                    <Trash2 className="h-4 w-4 mr-2" />
                    Tout supprimer
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle className="flex items-center gap-2">
                      <AlertTriangle className="h-5 w-5 text-destructive" />
                      Supprimer toutes les transactions ?
                    </AlertDialogTitle>
                    <AlertDialogDescription>
                      Cette action est irréversible.{' '}
                      {selectedPortfolio !== 'all'
                        ? `Les transactions du portefeuille sélectionné (${transactions?.length ?? 0}) seront`
                        : `Toutes vos transactions (${transactions?.length ?? 0}) seront`}{' '}
                      définitivement supprimées et les quantités des actifs concernés seront remises à zéro.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Annuler</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={() => deleteAllMutation.mutate()}
                      className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                      disabled={deleteAllMutation.isPending}
                    >
                      {deleteAllMutation.isPending ? (
                        <>
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                          Suppression...
                        </>
                      ) : (
                        'Supprimer tout'
                      )}
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Edit Transaction Dialog */}
      <EditTransactionForm
        transaction={editTransaction}
        open={editTransaction !== null}
        onOpenChange={(open) => !open && setEditTransaction(null)}
      />

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteTransaction !== null} onOpenChange={(open) => !open && setDeleteTransaction(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-destructive" />
              Supprimer cette transaction ?
            </AlertDialogTitle>
            <AlertDialogDescription>
              {deleteTransaction && (
                <span>
                  Voulez-vous vraiment supprimer la transaction{' '}
                  <strong>{typeLabels[deleteTransaction.transaction_type]}</strong> de{' '}
                  <strong>
                    {formatQuantity(deleteTransaction.quantity)} {deleteTransaction.asset_symbol}
                  </strong>{' '}
                  ?
                  <br />
                  Cette action est irréversible.
                </span>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annuler</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteTransaction && deleteMutation.mutate(deleteTransaction.id)}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Suppression...
                </>
              ) : (
                'Supprimer'
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
