import { useCallback, useEffect, useMemo, useState } from 'react'
import { usePortfolioList } from '@/features/portfolio/hooks'
import { getDateRangeStart, localDay } from './format'
import { TX_PAGE_SIZE, useTransactionPage } from './hooks'
import { sortTransactions } from './ledger'
import type { ServerFilters, SortDirection, SortField, Transaction } from './types'

export const ITEMS_PER_PAGE = 20

const orAll = (value: string) => (value !== 'all' ? value : undefined)

function useFilters() {
  const [portfolio, setPortfolio] = useState('all')
  const [asset, setAsset] = useState('all')
  const [platform, setPlatform] = useState('all')
  const [type, setType] = useState('all')
  const [search, setSearch] = useState('')
  const [dateRange, setDateRange] = useState('0')
  const [debouncedSearch, setDebouncedSearch] = useState('')

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search.trim()), 300)
    return () => clearTimeout(timer)
  }, [search])

  const server = useMemo<ServerFilters>(
    () => ({
      portfolio_id: orAll(portfolio),
      transaction_type: orAll(type),
      exchange: orAll(platform),
      asset_symbol: orAll(asset),
      date_from: localDay(getDateRangeStart(dateRange)),
      search: debouncedSearch || undefined,
    }),
    [portfolio, type, platform, asset, dateRange, debouncedSearch]
  )

  const active = [asset !== 'all', platform !== 'all', type !== 'all', dateRange !== '0', search !== ''].filter(Boolean).length

  const clear = () => {
    setAsset('all')
    setPlatform('all')
    setType('all')
    setDateRange('0')
    setSearch('')
  }

  return {
    values: { portfolio, asset, platform, type, search, dateRange },
    set: { portfolio: setPortfolio, asset: setAsset, platform: setPlatform, type: setType, search: setSearch, dateRange: setDateRange },
    server,
    active,
    clear,
  }
}

export type Filters = ReturnType<typeof useFilters>

function useLoadedTransactions(server: ServerFilters, skip: number) {
  const query = useTransactionPage(server, skip)
  const [loaded, setLoaded] = useState<Transaction[]>([])
  useEffect(() => {
    if (!query.data) return
    const items = query.data.items
    if (skip === 0) {
      setLoaded(items)
    } else {
      setLoaded((prev) => {
        const known = new Set(prev.map((t) => t.id))
        return [...prev, ...items.filter((t) => !known.has(t.id))]
      })
    }
  }, [query.data, skip])
  return { query, loaded, total: query.data?.total ?? loaded.length }
}

function useSelection() {
  const [ids, setIds] = useState<Set<string>>(new Set())
  const toggle = useCallback((id: string) => {
    setIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])
  const togglePage = (pageIds: string[]) => {
    const allSelected = pageIds.length > 0 && pageIds.every((id) => ids.has(id))
    setIds((prev) => {
      const next = new Set(prev)
      for (const id of pageIds) {
        if (allSelected) next.delete(id)
        else next.add(id)
      }
      return next
    })
  }
  const clear = useCallback(() => setIds(new Set()), [])
  return { ids, toggle, togglePage, clear }
}

export function useLedger() {
  const { data: portfolios } = usePortfolioList()
  const filters = useFilters()
  const [skip, setSkip] = useState(0)
  const { query, loaded, total } = useLoadedTransactions(filters.server, skip)
  const [page, setPage] = useState(1)
  const [sortField, setSortField] = useState<SortField>('date')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')
  const selection = useSelection()

  const sorted = useMemo(() => sortTransactions(loaded, sortField, sortDirection), [loaded, sortField, sortDirection])
  const pageCount = Math.max(1, Math.ceil(sorted.length / ITEMS_PER_PAGE))

  useEffect(() => {
    if (page > pageCount) setPage(pageCount)
  }, [page, pageCount])

  const visible = useMemo(() => sorted.slice((page - 1) * ITEMS_PER_PAGE, page * ITEMS_PER_PAGE), [sorted, page])

  const { portfolio, asset, platform, type, dateRange } = filters.values
  const debouncedSearch = filters.server.search
  const clearSelection = selection.clear
  useEffect(() => {
    setPage(1)
    setSkip(0)
    clearSelection()
  }, [portfolio, asset, platform, type, dateRange, debouncedSearch, clearSelection])

  const sortBy = (field: SortField) => {
    if (sortField === field) {
      setSortDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(field)
      setSortDirection('desc')
    }
  }

  return {
    portfolios: portfolios ?? [],
    filters,
    query,
    loaded,
    total,
    hasMore: loaded.length < total,
    loadMore: () => setSkip((s) => s + TX_PAGE_SIZE),
    sorted,
    visible,
    page,
    pageCount,
    setPage,
    sort: { field: sortField, direction: sortDirection, by: sortBy },
    selection,
  }
}

export type Ledger = ReturnType<typeof useLedger>
