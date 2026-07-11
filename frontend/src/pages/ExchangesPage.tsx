import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
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
} from '@/components/ui/alert-dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'
import { ToastAction } from '@/components/ui/toast'
import EmptyState from '@/components/ui/empty-state'
import { apiKeysApi, transactionsApi, type BalanceGap } from '@/services/api'
import ColdWalletsManager from '@/components/exchanges/ColdWalletsManager'
import ExchangeGuide from '@/components/exchanges/ExchangeGuide'
import { EXCHANGE_GUIDES } from '@/components/exchanges/exchange-guides'
import { invalidateAllFinancialData } from '@/lib/invalidate-queries'
import { queryKeys } from '@/lib/queryKeys'
import { formatDate, formatDateTime } from '@/lib/utils'
import { COLD_WALLETS } from '@/lib/platforms'
import {
  Plus,
  Key,
  Loader2,
  Trash2,
  RefreshCw,
  CheckCircle,
  XCircle,
  AlertCircle,
  Download,
  Coins,
  Calendar,
  Wallet,
  Shield,
  ChevronRight,
  Info,
  Link2,
  Pencil,
  Power,
  Scale,
} from 'lucide-react'

interface Exchange {
  id: string
  name: string
  requires_secret: boolean
  requires_passphrase: boolean
  description: string
}

interface APIKey {
  id: string
  exchange: string
  label: string | null
  is_active: boolean
  last_sync_at: string | null
  last_error: string | null
  created_at: string
}

interface TestResult {
  success: boolean
  message: string
  balance?: Record<string, number>
}

// Exchange logos — static lookups hoisted outside the component to avoid re-creation per render
const LOGO_URLS: Record<string, string> = {
  binance: '/logos/binance.png',
  kraken: '/logos/kraken.png',
  cryptocom: '/logos/cryptocom.svg',
  coinbase: '/logos/coinbase.svg',
  kucoin: '/logos/kucoin.svg',
  okx: '/logos/okx.svg',
  bybit: '/logos/bybit.svg',
  bitpanda: '/logos/bitpanda.svg',
  bitstamp: '/logos/bitstamp.svg',
  gateio: '/logos/gateio.svg',
}

const FALLBACK_COLORS: Record<string, string> = {
  binance: 'bg-[#F3BA2F]',
  kraken: 'bg-[oklch(var(--chart-2))]',
  coinbase: 'bg-[#0052FF]',
  cryptocom: 'bg-[#002D74]',
  kucoin: 'bg-[oklch(var(--chart-3))]',
  bybit: 'bg-[#F7A600]',
  okx: 'bg-[oklch(var(--foreground))]',
  bitpanda: 'bg-[oklch(var(--muted-foreground))]',
  bitstamp: 'bg-[oklch(var(--chart-3))]',
  gateio: 'bg-[oklch(var(--chart-5))]',
}

const FALLBACK_LABELS: Record<string, string> = {
  binance: 'BN',
  kraken: 'KR',
  coinbase: 'CB',
  cryptocom: 'CC',
  kucoin: 'KC',
  bybit: 'BY',
  okx: 'OK',
  bitpanda: 'BP',
  bitstamp: 'BS',
  gateio: 'GT',
}

const ExchangeLogo = ({ exchange, size = 40 }: { exchange: string; size?: number }) => {
  if (LOGO_URLS[exchange]) {
    return (
      <img
        src={LOGO_URLS[exchange]}
        alt={exchange}
        width={size}
        height={size}
        className="shrink-0 rounded-lg"
      />
    )
  }

  return (
    <div
      className={`${FALLBACK_COLORS[exchange] || 'bg-muted-foreground'} text-white rounded-xl flex items-center justify-center font-bold shrink-0`}
      style={{ width: size, height: size, fontSize: size * 0.35 }}
    >
      {FALLBACK_LABELS[exchange] || <Coins style={{ width: size * 0.5, height: size * 0.5 }} />}
    </div>
  )
}

export default function ExchangesPage() {
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const [showAddKey, setShowAddKey] = useState(false)
  const [selectedExchange, setSelectedExchange] = useState<string>('')
  const [testingId, setTestingId] = useState<string | null>(null)
  const [syncingId, setSyncingId] = useState<string | null>(null)
  const [importingId, setImportingId] = useState<string | null>(null)
  const [refreshingFxId, setRefreshingFxId] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<TestResult | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<APIKey | null>(null)
  const [renameTarget, setRenameTarget] = useState<APIKey | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [togglingId, setTogglingId] = useState<string | null>(null)
  // Un polling par tâche (import, recalcul FX...) : lancer une 2e opération
  // ne doit jamais écraser le suivi de la 1re.
  const pollTimersRef = useRef<
    Map<string, { interval: ReturnType<typeof setInterval>; timeout: ReturnType<typeof setTimeout> }>
  >(new Map())

  useEffect(() => {
    const timers = pollTimersRef.current
    return () => {
      timers.forEach(({ interval, timeout }) => {
        clearInterval(interval)
        clearTimeout(timeout)
      })
      timers.clear()
    }
  }, [])
  const [guideExchange, setGuideExchange] = useState<string | null>(null)
  // Panneau « Réconciliation » : dernier résultat de détection d'écarts
  // (vérification manuelle OU vérification auto post-import).
  const [gapCheck, setGapCheck] = useState<{ gaps: BalanceGap[]; checkedAt: Date } | null>(null)

  // Fetch supported exchanges
  const { data: exchanges } = useQuery<Exchange[]>({
    queryKey: queryKeys.exchanges.list,
    queryFn: apiKeysApi.listExchanges,
  })

  // Fetch user's API keys
  const { data: apiKeys, isLoading } = useQuery<APIKey[]>({
    queryKey: queryKeys.apiKeys.list,
    queryFn: apiKeysApi.list,
  })

  // Create API key mutation
  const createMutation = useMutation({
    mutationFn: apiKeysApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys.all })
      setShowAddKey(false)
      setSelectedExchange('')
      toast({ title: 'Clé API ajoutée', description: 'La clé API a été enregistrée avec succès.' })
    },
    onError: (error: unknown) => {
      const axiosError = error as import('axios').AxiosError<{ detail?: string }>
      toast({
        variant: 'destructive',
        title: 'Erreur',
        description: axiosError.response?.data?.detail || 'Impossible d\'ajouter la clé API.',
      })
    },
  })

  // Delete API key mutation
  const deleteMutation = useMutation({
    mutationFn: apiKeysApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys.all })
      invalidateAllFinancialData(queryClient)
      toast({ title: 'Clé API supprimée', description: 'La connexion a été supprimée avec succès.' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de supprimer la clé API.' })
    },
  })

  // Update API key mutation (rename label / toggle active)
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: { label?: string; is_active?: boolean } }) =>
      apiKeysApi.update(id, data),
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys.all })
      setRenameTarget(null)
      if (variables.data.is_active !== undefined) {
        toast({
          title: variables.data.is_active ? 'Connexion activée' : 'Connexion désactivée',
          description: variables.data.is_active
            ? 'La clé API sera de nouveau utilisée pour les synchronisations.'
            : 'La clé API ne sera plus utilisée pour les synchronisations.',
        })
      } else {
        toast({ title: 'Label mis à jour', description: 'La connexion a été renommée avec succès.' })
      }
    },
    onError: (error: unknown) => {
      const axiosError = error as import('axios').AxiosError<{ detail?: string }>
      toast({
        variant: 'destructive',
        title: 'Erreur',
        description: axiosError.response?.data?.detail || 'Impossible de mettre à jour la clé API.',
      })
    },
    onSettled: () => {
      setTogglingId(null)
    },
  })

  // Test API key mutation
  const testMutation = useMutation({
    mutationFn: apiKeysApi.test,
    onSuccess: (result: TestResult) => {
      setTestResult(result)
      queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys.all })
      if (result.success) {
        toast({ title: 'Connexion réussie', description: result.message })
      } else {
        toast({ variant: 'destructive', title: 'Échec de connexion', description: result.message })
      }
    },
    onError: (error: unknown) => {
      const axiosError = error as import('axios').AxiosError<{ detail?: string }>
      toast({
        variant: 'destructive',
        title: 'Erreur',
        description: axiosError.response?.data?.detail || 'Erreur lors du test.',
      })
    },
    onSettled: () => {
      setTestingId(null)
    },
  })

  // Sync mutation
  const syncMutation = useMutation({
    mutationFn: apiKeysApi.sync,
    onSuccess: (result: { synced_assets: number }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys.all })
      invalidateAllFinancialData(queryClient)
      toast({
        title: 'Synchronisation réussie',
        description: `${result.synced_assets} actif(s) synchronisé(s).`,
      })
    },
    onError: (error: unknown) => {
      const axiosError = error as import('axios').AxiosError<{ detail?: string }>
      toast({
        variant: 'destructive',
        title: 'Erreur de synchronisation',
        description: axiosError.response?.data?.detail || 'Impossible de synchroniser.',
      })
    },
    onSettled: () => {
      setSyncingId(null)
    },
  })

  // Import history — async Celery version with polling
  const importMutation = useMutation({
    mutationFn: apiKeysApi.importHistoryAsync,
    onSuccess: (result: { task_id: string; status: string }) => {
      toast({
        title: 'Import lancé',
        description: 'L\'import tourne en arrière-plan. Cela peut prendre quelques minutes.',
      })
      // Start polling
      pollImportStatus(result.task_id)
    },
    onError: (error: unknown) => {
      const axiosError = error as import('axios').AxiosError<{ detail?: string }>
      toast({
        variant: 'destructive',
        title: 'Erreur d\'import',
        description: axiosError.response?.data?.detail || 'Impossible de lancer l\'import.',
      })
      setImportingId(null)
    },
  })

  // Recompute historical FX on already-imported transactions (FIN-01 heal) — async + polling
  const refreshFxMutation = useMutation({
    mutationFn: apiKeysApi.refreshFx,
    onSuccess: (result: { task_id: string; status: string }) => {
      toast({
        title: 'Recalcul lancé',
        description: 'Les taux de change historiques sont recalculés en arrière-plan.',
      })
      pollImportStatus(result.task_id, {
        onClear: () => setRefreshingFxId(null),
        successTitle: 'Recalcul terminé',
        errorTitle: 'Erreur de recalcul',
        describe: (n) =>
          n > 0 ? `${n} transaction(s) corrigée(s)` : 'Aucune correction nécessaire',
      })
    },
    onError: (error: unknown) => {
      const axiosError = error as import('axios').AxiosError<{ detail?: string }>
      toast({
        variant: 'destructive',
        title: 'Erreur de recalcul',
        description: axiosError.response?.data?.detail || 'Impossible de lancer le recalcul.',
      })
      setRefreshingFxId(null)
    },
  })

  // Manual reconciliation check (Réconciliation card) — same wrapper as the
  // post-import detection, callable at any time.
  const gapsMutation = useMutation({
    mutationFn: () => transactionsApi.balanceGaps(5),
    onSuccess: (res) => {
      setGapCheck({ gaps: res.gaps, checkedAt: new Date() })
    },
    onError: () => {
      toast({
        variant: 'destructive',
        title: 'Erreur',
        description: 'Impossible de vérifier les écarts de solde.',
      })
    },
  })

  // Auto-credit detected gaps as AIRDROP transactions (same flow as the
  // post-import toast action), then re-check to refresh the panel.
  const creditGapsMutation = useMutation({
    mutationFn: () => transactionsApi.creditBalanceGaps(5),
    onSuccess: (result) => {
      toast({
        title: `${result.credited} récompense(s) créditée(s) en AIRDROP`,
        description:
          result.skipped > 0
            ? `${result.skipped} ignorée(s) (déjà créditées ou prix marché manquant).`
            : 'Vous pouvez les modifier depuis Transactions.',
      })
      invalidateAllFinancialData(queryClient)
      gapsMutation.mutate()
    },
    onError: (e: unknown) => {
      toast({
        variant: 'destructive',
        title: 'Erreur lors du crédit auto',
        description: e instanceof Error ? e.message : 'Inconnue',
      })
    },
  })

  // Polls a background task (import OR FX recalculation). `opts` lets the FX-recalc flow
  // reuse the exact same polling/cleanup with its own spinner and success wording.
  const pollImportStatus = (
    taskId: string,
    opts?: {
      onClear?: () => void
      successTitle?: string
      describe?: (synced: number) => string
      errorTitle?: string
    },
  ) => {
    const clear = opts?.onClear ?? (() => setImportingId(null))
    const stopPolling = () => {
      const timers = pollTimersRef.current.get(taskId)
      if (timers) {
        clearInterval(timers.interval)
        clearTimeout(timers.timeout)
        pollTimersRef.current.delete(taskId)
      }
    }

    const interval = setInterval(async () => {
      try {
        const status = await apiKeysApi.getImportStatus(taskId)

        if (status.status === 'completed') {
          stopPolling()
          clear()

          queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys.all })
          invalidateAllFinancialData(queryClient)

          const synced = status.synced ?? 0
          toast({
            title: opts?.successTitle ?? 'Import réussi',
            description: opts?.describe
              ? opts.describe(synced)
              : synced > 0
                ? `${synced} transaction(s) synchronisée(s)`
                : 'Aucune nouvelle transaction',
          })

          // Post-sync reconciliation: surface holdings the exchange reports
          // but the sync didn't import as transactions (Binance reward
          // vouchers, unrecognized airdrops). Offers a 1-click auto-credit.
          transactionsApi
            .balanceGaps(5)
            .then((res) => {
              // Keep the persistent Réconciliation panel in sync with the
              // automatic post-import check.
              setGapCheck({ gaps: res.gaps, checkedAt: new Date() })
              if (res.count > 0) {
                const totalEur = res.gaps.reduce((s, g) => s + g.missing_eur, 0)
                const top = res.gaps
                  .slice(0, 3)
                  .map((g) => `${g.symbol} (${g.missing_eur.toFixed(2)} €)`)
                  .join(', ')
                const hasEarn = res.gaps.some((g) => g.source_hint === 'earn_pending')
                toast({
                  title: `${res.count} récompense(s) non tracée(s) détectée(s)`,
                  description:
                    `Total estimé: ${totalEur.toFixed(2)} €. Top: ${top}.` +
                    (hasEarn ? ' (probables intérêts Earn)' : ''),
                  action: (
                    <ToastAction
                      altText="Crediter automatiquement les récompenses en AIRDROP"
                      onClick={() => creditGapsMutation.mutate()}
                    >
                      Crediter auto
                    </ToastAction>
                  ),
                })
              }
            })
            .catch(() => {
              /* non-blocking: silently skip if endpoint is unavailable */
            })
        } else if (status.status === 'failed') {
          stopPolling()
          clear()

          toast({
            variant: 'destructive',
            title: opts?.errorTitle ?? 'Erreur d\'import',
            description: status.error || 'L\'opération a échoué.',
          })
        }
        // else: still pending/progress — continue polling
      } catch {
        stopPolling()
        clear()

        toast({
          variant: 'destructive',
          title: 'Erreur',
          description: 'Impossible de vérifier le statut de l\'opération.',
        })
      }
    }, 5000) // Poll every 5 seconds

    // Safety: stop polling after 10 minutes
    const timeout = setTimeout(() => {
      stopPolling()
      clear()
    }, 600000)

    pollTimersRef.current.set(taskId, { interval, timeout })
  }

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const formData = new FormData(e.currentTarget)

    createMutation.mutate({
      exchange: selectedExchange,
      label: formData.get('label') as string || undefined,
      api_key: formData.get('api_key') as string,
      secret_key: formData.get('secret_key') as string || undefined,
      passphrase: formData.get('passphrase') as string || undefined,
    })
  }

  const handleDelete = () => {
    if (deleteTarget) {
      deleteMutation.mutate(deleteTarget.id)
      setDeleteTarget(null)
    }
  }

  const selectedExchangeInfo = exchanges?.find((e) => e.id === selectedExchange)

  const getExchangeName = (exchangeId: string) => {
    return exchanges?.find((e) => e.id === exchangeId)?.name || exchangeId
  }

  // Format balance for display
  const formatBalance = (amount: number) => {
    if (amount === 0) return '0'
    if (amount < 0.00001) return amount.toExponential(2)
    if (amount < 1) return amount.toFixed(6)
    if (amount < 1000) return amount.toFixed(4)
    return amount.toLocaleString('fr-FR', { maximumFractionDigits: 2 })
  }

  // Freshness of the last sync: relative label + color (gain <24h, warning 1-3j, loss >3j)
  const getSyncFreshness = (dateString: string): { label: string; className: string } | null => {
    const ts = new Date(dateString).getTime()
    if (Number.isNaN(ts)) return null
    const diffMs = Date.now() - ts
    if (diffMs < 0) return null
    const hours = Math.floor(diffMs / 3_600_000)
    const days = Math.floor(hours / 24)
    const label =
      hours < 1 ? 'il y a moins d\'1 h' : hours < 24 ? `il y a ${hours} h` : `il y a ${days} j`
    const className =
      hours < 24
        ? 'text-gain border-gain/30 bg-gain/10'
        : days <= 3
          ? 'text-warning border-warning/30 bg-warning/10'
          : 'text-loss border-loss/30 bg-loss/10'
    return { label, className }
  }

  // Count connected exchanges by type
  const getExchangeCount = (exchangeId: string) => {
    return apiKeys?.filter(k => k.exchange === exchangeId).length || 0
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-serif font-medium">Exchanges</h1>
          <p className="text-muted-foreground">
            Connectez vos exchanges pour synchroniser automatiquement vos positions.
          </p>
        </div>
        <Button onClick={() => setShowAddKey(true)} className="w-full sm:w-auto">
          <Plus className="h-4 w-4 mr-2" />
          Connecter un exchange
        </Button>
      </div>

      {/* Connected exchanges */}
      {apiKeys && apiKeys.length > 0 ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {apiKeys.map((apiKey) => {
            const sameExchangeCount = getExchangeCount(apiKey.exchange)
            const sameExchangeIndex = apiKeys
              .filter(k => k.exchange === apiKey.exchange)
              .findIndex(k => k.id === apiKey.id) + 1

            return (
              <Card key={apiKey.id} elevation="raised" className="relative overflow-hidden">
                {/* Status indicator bar */}
                <div className={`absolute top-0 left-0 right-0 h-1 ${apiKey.is_active ? 'bg-gain' : 'bg-loss'}`} />

                <CardHeader className="pb-3 pt-5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <ExchangeLogo exchange={apiKey.exchange} size={48} />
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <CardTitle className="text-lg truncate">
                            {getExchangeName(apiKey.exchange)}
                          </CardTitle>
                          {sameExchangeCount > 1 && (
                            <Badge variant="secondary" className="text-xs">
                              #{sameExchangeIndex}
                            </Badge>
                          )}
                        </div>
                        {apiKey.label ? (
                          <p className="text-sm text-muted-foreground truncate">{apiKey.label}</p>
                        ) : (
                          <p className="text-sm text-muted-foreground italic">Sans label</p>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-muted-foreground"
                        title="Renommer cette connexion"
                        onClick={() => {
                          setRenameTarget(apiKey)
                          setRenameValue(apiKey.label || '')
                        }}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <button
                        type="button"
                        title={apiKey.is_active
                          ? 'Cliquer pour désactiver cette connexion'
                          : 'Cliquer pour réactiver cette connexion'}
                        onClick={() => {
                          setTogglingId(apiKey.id)
                          updateMutation.mutate({ id: apiKey.id, data: { is_active: !apiKey.is_active } })
                        }}
                        disabled={togglingId === apiKey.id}
                        className="disabled:opacity-50"
                      >
                        <Badge variant={apiKey.is_active ? 'default' : 'destructive'} className="cursor-pointer gap-1">
                          {togglingId === apiKey.id ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <Power className="h-3 w-3" />
                          )}
                          {apiKey.is_active ? 'Actif' : 'Inactif'}
                        </Badge>
                      </button>
                    </div>
                  </div>
                </CardHeader>

                <CardContent className="space-y-4">
                  {/* Info badges */}
                  <div className="flex flex-wrap gap-2 text-xs">
                    <div className="flex items-center gap-1 text-muted-foreground bg-muted px-2 py-1 rounded-md">
                      <Calendar className="h-3 w-3" />
                      <span>Créé le {formatDate(apiKey.created_at)}</span>
                    </div>
                    {apiKey.last_sync_at && (
                      <>
                        <div className="flex items-center gap-1 text-muted-foreground bg-muted px-2 py-1 rounded-md">
                          <RefreshCw className="h-3 w-3" />
                          <span>Sync {formatDateTime(apiKey.last_sync_at)}</span>
                        </div>
                        {(() => {
                          const freshness = getSyncFreshness(apiKey.last_sync_at)
                          if (!freshness) return null
                          return (
                            <Badge variant="outline" className={`text-xs font-medium ${freshness.className}`}>
                              {freshness.label}
                            </Badge>
                          )
                        })()}
                      </>
                    )}
                  </div>

                  {/* Error message */}
                  {apiKey.last_error && (
                    <div className="flex items-start gap-2 text-sm text-loss bg-loss/10 p-2 rounded-md">
                      <AlertCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
                      <span className="line-clamp-2">{apiKey.last_error}</span>
                    </div>
                  )}

                  {/* Action buttons */}
                  <div className="grid grid-cols-4 gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      className="flex flex-col h-auto py-2 gap-1"
                      onClick={() => {
                        setTestingId(apiKey.id)
                        testMutation.mutate(apiKey.id)
                      }}
                      disabled={testingId === apiKey.id}
                    >
                      {testingId === apiKey.id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Key className="h-4 w-4" />
                      )}
                      <span className="text-xs">Tester</span>
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="flex flex-col h-auto py-2 gap-1"
                      onClick={() => {
                        setSyncingId(apiKey.id)
                        syncMutation.mutate(apiKey.id)
                      }}
                      disabled={syncingId === apiKey.id}
                    >
                      {syncingId === apiKey.id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <RefreshCw className="h-4 w-4" />
                      )}
                      <span className="text-xs">Sync</span>
                    </Button>
                    <Button
                      variant="default"
                      size="sm"
                      className="flex flex-col h-auto py-2 gap-1"
                      onClick={() => {
                        setImportingId(apiKey.id)
                        importMutation.mutate(apiKey.id)
                      }}
                      disabled={importingId === apiKey.id}
                    >
                      {importingId === apiKey.id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Download className="h-4 w-4" />
                      )}
                      <span className="text-xs">Import</span>
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="flex flex-col h-auto py-2 gap-1 text-destructive hover:text-destructive hover:bg-destructive/10"
                      onClick={() => setDeleteTarget(apiKey)}
                    >
                      <Trash2 className="h-4 w-4" />
                      <span className="text-xs">Suppr.</span>
                    </Button>
                  </div>

                  {/* Maintenance: recompute historical FX on already-imported transactions */}
                  <Button
                    variant="outline"
                    size="sm"
                    className="mt-2 w-full gap-2 text-xs text-muted-foreground"
                    title="Recalcule le taux de change historique (USD→EUR) du coût de revient sur vos transactions déjà importées, sans rien supprimer."
                    onClick={() => {
                      setRefreshingFxId(apiKey.id)
                      refreshFxMutation.mutate(apiKey.id)
                    }}
                    disabled={refreshingFxId === apiKey.id}
                  >
                    {refreshingFxId === apiKey.id ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Coins className="h-4 w-4" />
                    )}
                    Recalculer les taux de change
                  </Button>
                </CardContent>
              </Card>
            )
          })}
        </div>
      ) : (
        <EmptyState
          icon={Link2}
          title="Aucun exchange connecté"
          description="Connectez vos exchanges pour importer automatiquement vos positions crypto."
          action={
            <Button onClick={() => setShowAddKey(true)}>
              <Plus className="h-4 w-4 mr-2" />
              Connecter un exchange
            </Button>
          }
        />
      )}

      {/* Cold Wallets section */}
      <Card elevation="raised">
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Shield className="h-5 w-5 text-accent" />
            Mes wallets
          </CardTitle>
          <CardDescription>
            Portefeuilles matériels et wallets auto-custodial. Suivi manuel de vos actifs.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {COLD_WALLETS.map((wallet) => {
              const walletColors: Record<string, string> = {
                Tangem: 'bg-[oklch(var(--foreground))]',
                Ledger: 'bg-[oklch(var(--foreground))]',
                Trezor: 'bg-[oklch(var(--chart-3))]',
                SafePal: 'bg-[oklch(var(--chart-2))]',
                Metamask: 'bg-[#E2761B]',
              }
              const walletLabels: Record<string, string> = {
                Tangem: 'TG',
                Ledger: 'LG',
                Trezor: 'TZ',
                SafePal: 'SP',
                Metamask: 'MM',
              }
              return (
                <div
                  key={wallet}
                  className="flex items-center gap-3 p-4 rounded-lg border bg-muted/30"
                >
                  <div
                    className={`${walletColors[wallet] || 'bg-muted-foreground'} text-white rounded-xl flex items-center justify-center font-bold shrink-0`}
                    style={{ width: 40, height: 40, fontSize: 14 }}
                  >
                    {walletLabels[wallet] || <Shield style={{ width: 20, height: 20 }} />}
                  </div>
                  <div className="flex-1">
                    <h3 className="font-medium">{wallet}</h3>
                    <p className="text-xs text-muted-foreground">Suivi manuel</p>
                  </div>
                  <Badge variant="outline" className="text-xs text-accent border-accent/30">
                    <Shield className="h-3 w-3 mr-1" />
                    Self-custody
                  </Badge>
                </div>
              )
            })}
          </div>
          <p className="text-xs text-muted-foreground mt-4">
            Pour ajouter des actifs sur un wallet, allez dans votre portefeuille et enregistrez un transfert entrant avec la plateforme source.
          </p>
        </CardContent>
      </Card>

      {/* Cold wallet address → name routing (drives the auto-mirror destination) */}
      <ColdWalletsManager />

      {/* Actions explanation */}
      <Card elevation="raised" className="bg-muted/30">
        <CardHeader>
          <CardTitle className="text-lg">Comment ça marche ?</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center">
                  <Key className="h-4 w-4 text-muted-foreground" />
                </div>
                <span className="font-medium">Tester</span>
              </div>
              <p className="text-sm text-muted-foreground">
                Vérifie que vos clés API fonctionnent et affiche vos soldes actuels.
              </p>
            </div>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center">
                  <RefreshCw className="h-4 w-4 text-muted-foreground" />
                </div>
                <span className="font-medium">Sync</span>
              </div>
              <p className="text-sm text-muted-foreground">
                Met à jour les quantités de vos actifs depuis l'exchange.
              </p>
            </div>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <div className="h-8 w-8 rounded-full bg-primary/20 flex items-center justify-center">
                  <Download className="h-4 w-4 text-primary" />
                </div>
                <span className="font-medium">Import</span>
              </div>
              <p className="text-sm text-muted-foreground">
                Importe l'historique complet : trades, achats fiat, rewards et staking.
              </p>
            </div>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <div className="h-8 w-8 rounded-full bg-destructive/20 flex items-center justify-center">
                  <Trash2 className="h-4 w-4 text-destructive" />
                </div>
                <span className="font-medium">Supprimer</span>
              </div>
              <p className="text-sm text-muted-foreground">
                Retire la connexion. Vos données importées restent dans l'app.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Supported exchanges info */}
      <Card elevation="raised">
        <CardHeader>
          <CardTitle>Exchanges supportés</CardTitle>
          <CardDescription>
            Cliquez sur un exchange pour voir le guide de création de clé API.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {exchanges?.map((exchange) => {
              const connectedCount = getExchangeCount(exchange.id)
              return (
                <button
                  key={exchange.id}
                  type="button"
                  onClick={() => setGuideExchange(exchange.id)}
                  className="flex items-start gap-3 p-4 rounded-lg border bg-muted/30 hover:bg-muted/50 hover:border-primary/30 transition-colors text-left group cursor-pointer"
                >
                  <ExchangeLogo exchange={exchange.id} size={40} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="font-medium">{exchange.name}</h3>
                      {connectedCount > 0 && (
                        <Badge variant="outline" className="text-xs">
                          {connectedCount} connecté{connectedCount > 1 ? 's' : ''}
                        </Badge>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground mt-1">
                      {exchange.description}
                    </p>
                    <p className="text-xs text-primary mt-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Info className="h-3 w-3" />
                      Voir le guide de connexion
                    </p>
                  </div>
                  <ChevronRight className="h-4 w-4 text-muted-foreground mt-1 opacity-0 group-hover:opacity-100 transition-opacity" />
                </button>
              )
            })}
          </div>
        </CardContent>
      </Card>

      {/* Reconciliation panel: persistent view of untracked-reward detection
          (previously only surfaced in a 5 s post-import toast) */}
      <Card elevation="raised">
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Scale className="h-5 w-5 text-accent" />
            Réconciliation
          </CardTitle>
          <CardDescription>
            Compare les soldes rapportés par vos exchanges avec vos transactions importées pour
            détecter les récompenses non tracées (intérêts Earn, airdrops, vouchers...).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <Button
              variant="outline"
              onClick={() => gapsMutation.mutate()}
              disabled={gapsMutation.isPending}
              className="w-full sm:w-auto gap-2"
            >
              {gapsMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              Vérifier les écarts
            </Button>
            {gapCheck && (
              <span className="text-xs text-muted-foreground">
                Dernière vérification : {formatDateTime(gapCheck.checkedAt.toISOString())}
              </span>
            )}
          </div>

          {!gapCheck && (
            <p className="text-sm text-muted-foreground">
              Cliquez sur « Vérifier les écarts » pour lancer une comparaison. Une vérification
              est aussi effectuée automatiquement après chaque import d'historique.
            </p>
          )}

          {gapCheck && gapCheck.gaps.length === 0 && (
            <div className="flex items-center gap-2 text-sm text-gain bg-gain/10 p-3 rounded-md">
              <CheckCircle className="h-4 w-4 shrink-0" />
              <span>Aucun écart détecté ✓</span>
            </div>
          )}

          {gapCheck && gapCheck.gaps.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-start gap-2 text-sm text-warning bg-warning/10 p-3 rounded-md">
                <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                <span>
                  {gapCheck.gaps.length} récompense(s) non tracée(s) détectée(s) — total estimé
                  {' '}
                  {gapCheck.gaps.reduce((s, g) => s + g.missing_eur, 0).toFixed(2)} €.
                </span>
              </div>
              <div className="overflow-x-auto rounded-lg border">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-muted/50 text-left text-xs text-muted-foreground">
                      <th className="px-3 py-2 font-medium">Actif</th>
                      <th className="px-3 py-2 font-medium">Exchange</th>
                      <th className="px-3 py-2 font-medium text-right">Écart de quantité</th>
                      <th className="px-3 py-2 font-medium text-right">Valorisation estimée</th>
                      <th className="px-3 py-2 font-medium">Origine probable</th>
                    </tr>
                  </thead>
                  <tbody>
                    {gapCheck.gaps.map((gap) => (
                      <tr key={`${gap.asset_id}-${gap.exchange}`} className="border-b last:border-b-0">
                        <td className="px-3 py-2 font-medium">{gap.symbol}</td>
                        <td className="px-3 py-2 text-muted-foreground">{gap.exchange}</td>
                        <td className="px-3 py-2 text-right font-mono">
                          +{formatBalance(gap.missing_qty)}
                        </td>
                        <td className="px-3 py-2 text-right font-mono">
                          {gap.missing_eur.toFixed(2)} €
                        </td>
                        <td className="px-3 py-2 text-muted-foreground">
                          {gap.source_hint === 'earn_pending'
                            ? 'Intérêts Earn'
                            : gap.source_hint === 'airdrop'
                              ? 'Airdrop'
                              : 'Inconnue'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Button
                onClick={() => creditGapsMutation.mutate()}
                disabled={creditGapsMutation.isPending}
                className="gap-2"
              >
                {creditGapsMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Coins className="h-4 w-4" />
                )}
                Créditer en airdrop
              </Button>
            </div>
          )}

          <p className="text-xs text-muted-foreground flex items-start gap-1.5">
            <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            <span>
              Le crédit auto valorise au prix du jour — pour des revenus perçus antérieurement,
              la base fiscale exacte est le prix au jour de perception.
            </span>
          </p>
        </CardContent>
      </Card>

      {/* Add API Key Dialog */}
      <Dialog open={showAddKey} onOpenChange={setShowAddKey}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Connecter un exchange</DialogTitle>
            <DialogDescription>
              Entrez vos clés API pour connecter votre exchange.
              Utilisez des clés en lecture seule pour plus de sécurité.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSubmit}>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="exchange">Exchange</Label>
                <Select
                  value={selectedExchange}
                  onValueChange={setSelectedExchange}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Sélectionner un exchange" />
                  </SelectTrigger>
                  <SelectContent>
                    {exchanges?.map((exchange) => (
                      <SelectItem key={exchange.id} value={exchange.id}>
                        <div className="flex items-center gap-2">
                          <ExchangeLogo exchange={exchange.id} size={20} />
                          <span>{exchange.name}</span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="label">Label (optionnel)</Label>
                <Input
                  id="label"
                  name="label"
                  placeholder="Ex: Compte principal, DCA, Trading..."
                />
                <p className="text-xs text-muted-foreground">
                  Utile si vous avez plusieurs comptes sur le même exchange.
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="api_key">Clé API</Label>
                <Input
                  id="api_key"
                  name="api_key"
                  type="password"
                  placeholder="Votre clé API"
                  required
                />
              </div>

              {selectedExchangeInfo?.requires_secret && (
                <div className="space-y-2">
                  <Label htmlFor="secret_key">Clé secrète</Label>
                  <Input
                    id="secret_key"
                    name="secret_key"
                    type="password"
                    placeholder="Votre clé secrète"
                  />
                </div>
              )}

              {selectedExchangeInfo?.requires_passphrase && (
                <div className="space-y-2">
                  <Label htmlFor="passphrase">Passphrase</Label>
                  <Input
                    id="passphrase"
                    name="passphrase"
                    type="password"
                    placeholder="Votre passphrase"
                  />
                </div>
              )}

              <div className="rounded-lg bg-warning/10 border border-warning/20 p-3 text-sm">
                <p className="text-warning dark:text-warning">
                  <strong>Conseil sécurité:</strong> Créez des clés API en lecture seule
                  sans permission de retrait pour protéger vos fonds.
                </p>
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setShowAddKey(false)}>
                Annuler
              </Button>
              <Button type="submit" disabled={!selectedExchange || createMutation.isPending}>
                {createMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Connecter
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Test Result Dialog */}
      <Dialog open={!!testResult} onOpenChange={() => setTestResult(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {testResult?.success ? (
                <CheckCircle className="h-5 w-5 text-gain" />
              ) : (
                <XCircle className="h-5 w-5 text-loss" />
              )}
              {testResult?.success ? 'Connexion réussie' : 'Échec de connexion'}
            </DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <p className="text-muted-foreground">{testResult?.message}</p>
            {testResult?.balance && Object.keys(testResult.balance).length > 0 && (
              <div className="mt-4">
                <div className="flex items-center gap-2 mb-3">
                  <Wallet className="h-4 w-4 text-muted-foreground" />
                  <p className="font-medium">Soldes détectés ({Object.keys(testResult.balance).length} actifs)</p>
                </div>
                <div className="grid gap-2 max-h-64 overflow-y-auto pr-2">
                  {Object.entries(testResult.balance)
                    .sort((a, b) => b[1] - a[1])
                    .map(([symbol, amount]) => (
                      <div
                        key={symbol}
                        className="flex justify-between items-center bg-muted p-2 rounded-md"
                      >
                        <span className="font-medium">{symbol}</span>
                        <span className="font-mono text-sm">
                          {formatBalance(amount)}
                        </span>
                      </div>
                    ))}
                </div>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button onClick={() => setTestResult(null)}>Fermer</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* API Key Guide Dialog */}
      <Dialog open={!!guideExchange} onOpenChange={() => setGuideExchange(null)}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          {guideExchange && EXCHANGE_GUIDES[guideExchange] && (
            <ExchangeGuide
              guide={EXCHANGE_GUIDES[guideExchange]}
              logo={<ExchangeLogo exchange={guideExchange} size={32} />}
              onClose={() => setGuideExchange(null)}
              onConnect={() => {
                setGuideExchange(null)
                setShowAddKey(true)
                setSelectedExchange(guideExchange)
              }}
            />
          )}

          {guideExchange && !EXCHANGE_GUIDES[guideExchange] && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-3">
                  <ExchangeLogo exchange={guideExchange} size={32} />
                  {exchanges?.find(e => e.id === guideExchange)?.name}
                </DialogTitle>
              </DialogHeader>
              <div className="py-4 text-sm text-muted-foreground">
                <p>Le guide pour cet exchange n'est pas encore disponible.</p>
                <p className="mt-2">En général, rendez-vous dans les paramètres de sécurité/API de votre exchange et créez une clé en <strong>lecture seule</strong>.</p>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setGuideExchange(null)}>
                  Fermer
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* Rename API Key Dialog */}
      <Dialog open={!!renameTarget} onOpenChange={(open) => !open && setRenameTarget(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Renommer la connexion</DialogTitle>
            <DialogDescription>
              {renameTarget && (
                <>
                  Modifiez le label de votre connexion{' '}
                  <strong>{getExchangeName(renameTarget.exchange)}</strong>.
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              if (!renameTarget) return
              updateMutation.mutate({ id: renameTarget.id, data: { label: renameValue.trim() } })
            }}
          >
            <div className="space-y-2 py-4">
              <Label htmlFor="rename-label">Label</Label>
              <Input
                id="rename-label"
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                placeholder="Ex: Compte principal, DCA, Trading..."
                autoFocus
              />
              <p className="text-xs text-muted-foreground">
                Utile si vous avez plusieurs comptes sur le même exchange.
              </p>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setRenameTarget(null)}>
                Annuler
              </Button>
              <Button type="submit" disabled={updateMutation.isPending}>
                {updateMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Enregistrer
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Supprimer cette connexion ?</AlertDialogTitle>
            <AlertDialogDescription>
              Vous êtes sur le point de supprimer la connexion à{' '}
              <strong>{deleteTarget && getExchangeName(deleteTarget.exchange)}</strong>
              {deleteTarget?.label && <> ({deleteTarget.label})</>}.
              <br /><br />
              Vos données importées (transactions, actifs) resteront dans l'application.
              Vous pourrez reconnecter cet exchange à tout moment.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annuler</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Supprimer
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
