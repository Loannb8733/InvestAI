import { useState } from 'react'
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
import { apiKeysApi } from '@/services/api'
import { invalidateAllFinancialData } from '@/lib/invalidate-queries'
import { queryKeys } from '@/lib/queryKeys'
import { formatDate } from '@/lib/utils'
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
  ExternalLink,
  ShieldCheck,
  Shield,
  Copy,
  ChevronRight,
  Info,
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

// Exchange logos component with local SVG logos
const ExchangeLogo = ({ exchange, size = 40 }: { exchange: string; size?: number }) => {
  const logoUrls: Record<string, string> = {
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

  const fallbackColors: Record<string, string> = {
    binance: 'bg-[#F3BA2F]',
    kraken: 'bg-[#5741D9]',
    coinbase: 'bg-[#0052FF]',
    cryptocom: 'bg-[#002D74]',
    kucoin: 'bg-[#23AF91]',
    bybit: 'bg-[#F7A600]',
    okx: 'bg-[#000000]',
    bitpanda: 'bg-[#5A6773]',
    bitstamp: 'bg-[#4A9F3F]',
    gateio: 'bg-[#2354E6]',
  }

  const fallbackLabels: Record<string, string> = {
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

  if (logoUrls[exchange]) {
    return (
      <img
        src={logoUrls[exchange]}
        alt={exchange}
        width={size}
        height={size}
        className="shrink-0 rounded-lg"
      />
    )
  }

  return (
    <div
      className={`${fallbackColors[exchange] || 'bg-primary/20'} text-white rounded-xl flex items-center justify-center font-bold shrink-0`}
      style={{ width: size, height: size, fontSize: size * 0.35 }}
    >
      {fallbackLabels[exchange] || <Coins style={{ width: size * 0.5, height: size * 0.5 }} />}
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
  const [testResult, setTestResult] = useState<TestResult | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<APIKey | null>(null)
  const [guideExchange, setGuideExchange] = useState<string | null>(null)

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

  // Import history mutation
  const importMutation = useMutation({
    mutationFn: apiKeysApi.importHistory,
    onSuccess: (result: {
      fiat_orders: number
      rewards: number
      spot_trades: number
      assets_created: number
      debug?: { spot_trades_count: number; fiat_orders_count: number; convert_orders_count: number }
    }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys.all })
      invalidateAllFinancialData(queryClient)

      const details = []
      if (result.fiat_orders > 0) details.push(`${result.fiat_orders} achat(s)`)
      if (result.rewards > 0) details.push(`${result.rewards} reward(s)`)
      if (result.spot_trades > 0) details.push(`${result.spot_trades} trade(s) spot`)
      if (result.assets_created > 0) details.push(`${result.assets_created} actif(s) créé(s)`)

      let description = details.length > 0 ? details.join(', ') : 'Aucune nouvelle transaction'
      if (result.debug && details.length === 0) {
        const debugParts = []
        if (result.debug.spot_trades_count > 0) debugParts.push(`${result.debug.spot_trades_count} trades spot`)
        if (result.debug.fiat_orders_count > 0) debugParts.push(`${result.debug.fiat_orders_count} ordres fiat`)
        if (result.debug.convert_orders_count > 0) debugParts.push(`${result.debug.convert_orders_count} conversions`)
        description += debugParts.length > 0 ? ` (trouvé: ${debugParts.join(', ')})` : ' (aucune donnée trouvée)'
      }

      toast({
        title: 'Import réussi',
        description,
      })
    },
    onError: (error: unknown) => {
      const axiosError = error as import('axios').AxiosError<{ detail?: string }>
      toast({
        variant: 'destructive',
        title: 'Erreur d\'import',
        description: axiosError.response?.data?.detail || 'Impossible d\'importer l\'historique.',
      })
    },
    onSettled: () => {
      setImportingId(null)
    },
  })

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
          <h1 className="text-3xl font-bold">Exchanges</h1>
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
              <Card key={apiKey.id} className="relative overflow-hidden">
                {/* Status indicator bar */}
                <div className={`absolute top-0 left-0 right-0 h-1 ${apiKey.is_active ? 'bg-green-500' : 'bg-red-500'}`} />

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
                    <Badge variant={apiKey.is_active ? 'default' : 'destructive'} className="shrink-0">
                      {apiKey.is_active ? 'Actif' : 'Inactif'}
                    </Badge>
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
                      <div className="flex items-center gap-1 text-muted-foreground bg-muted px-2 py-1 rounded-md">
                        <RefreshCw className="h-3 w-3" />
                        <span>Sync {formatDate(apiKey.last_sync_at)}</span>
                      </div>
                    )}
                  </div>

                  {/* Error message */}
                  {apiKey.last_error && (
                    <div className="flex items-start gap-2 text-sm text-red-500 bg-red-500/10 p-2 rounded-md">
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
                </CardContent>
              </Card>
            )
          })}
        </div>
      ) : (
        <Card>
          <CardContent className="py-12">
            <div className="text-center space-y-4">
              <div className="flex justify-center gap-4">
                <ExchangeLogo exchange="binance" size={48} />
                <ExchangeLogo exchange="kraken" size={48} />
              </div>
              <h2 className="text-xl font-semibold">Aucun exchange connecté</h2>
              <p className="text-muted-foreground max-w-md mx-auto">
                Connectez vos exchanges pour importer automatiquement vos positions crypto.
              </p>
              <Button onClick={() => setShowAddKey(true)}>
                <Plus className="h-4 w-4 mr-2" />
                Connecter un exchange
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Cold Wallets section */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Shield className="h-5 w-5 text-blue-500" />
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
                Tangem: 'bg-[#000000]',
                Ledger: 'bg-[#000000]',
                Trezor: 'bg-[#00854D]',
                SafePal: 'bg-[#4A33D0]',
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
                    className={`${walletColors[wallet] || 'bg-blue-500/20'} text-white rounded-xl flex items-center justify-center font-bold shrink-0`}
                    style={{ width: 40, height: 40, fontSize: 14 }}
                  >
                    {walletLabels[wallet] || <Shield style={{ width: 20, height: 20 }} />}
                  </div>
                  <div className="flex-1">
                    <h3 className="font-medium">{wallet}</h3>
                    <p className="text-xs text-muted-foreground">Suivi manuel</p>
                  </div>
                  <Badge variant="outline" className="text-xs text-blue-500 border-blue-500/30">
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

      {/* Actions explanation */}
      <Card className="bg-muted/30">
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
      <Card>
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

              <div className="rounded-lg bg-yellow-500/10 border border-yellow-500/20 p-3 text-sm">
                <p className="text-yellow-600 dark:text-yellow-500">
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
                <CheckCircle className="h-5 w-5 text-green-500" />
              ) : (
                <XCircle className="h-5 w-5 text-red-500" />
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
          {guideExchange === 'binance' && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-3">
                  <ExchangeLogo exchange="binance" size={32} />
                  Créer une clé API sur Binance
                </DialogTitle>
                <DialogDescription>
                  Suivez ces étapes pour générer une clé API en lecture seule.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-6 py-4">
                <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-4">
                  <div className="flex items-start gap-3">
                    <ShieldCheck className="h-5 w-5 text-yellow-500 mt-0.5 shrink-0" />
                    <div className="text-sm">
                      <p className="font-medium text-yellow-600 dark:text-yellow-400">Important : lecture seule</p>
                      <p className="text-muted-foreground mt-1">
                        Ne cochez <strong>jamais</strong> les permissions de retrait ou de trading.
                        InvestAI a uniquement besoin de <strong>lire</strong> vos soldes et votre historique.
                      </p>
                    </div>
                  </div>
                </div>

                <ol className="space-y-5">
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">1</span>
                    <div>
                      <p className="font-medium">Connectez-vous à votre compte Binance</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Rendez-vous sur <a href="https://www.binance.com/fr/my/settings/api-management" target="_blank" rel="noopener noreferrer" className="text-primary underline inline-flex items-center gap-1">binance.com &gt; Gestion API <ExternalLink className="h-3 w-3" /></a>
                      </p>
                      <p className="text-sm text-muted-foreground">
                        Ou : icône profil en haut à droite &gt; <strong>Gestion API</strong>
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">2</span>
                    <div>
                      <p className="font-medium">Créez une nouvelle clé API</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Cliquez sur <strong>"Créer une API"</strong>, choisissez <strong>"Clé API générée par le système"</strong>,
                        puis donnez-lui un nom (ex: "InvestAI").
                      </p>
                      <p className="text-sm text-muted-foreground">
                        Binance vous demandera une vérification 2FA (email + authenticator).
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">3</span>
                    <div>
                      <p className="font-medium">Configurez les permissions</p>
                      <p className="text-sm text-muted-foreground mt-1">Cochez uniquement :</p>
                      <div className="mt-2 space-y-1.5">
                        <div className="flex items-center gap-2 text-sm">
                          <CheckCircle className="h-4 w-4 text-green-500" />
                          <span><strong>Lecture seule</strong> (Enable Reading)</span>
                        </div>
                      </div>
                      <div className="mt-2 space-y-1.5">
                        <p className="text-sm text-muted-foreground">Ne cochez <strong>PAS</strong> :</p>
                        <div className="flex items-center gap-2 text-sm">
                          <XCircle className="h-4 w-4 text-red-500" />
                          <span className="text-muted-foreground">Enable Spot & Margin Trading</span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <XCircle className="h-4 w-4 text-red-500" />
                          <span className="text-muted-foreground">Enable Withdrawals</span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <XCircle className="h-4 w-4 text-red-500" />
                          <span className="text-muted-foreground">Enable Futures</span>
                        </div>
                      </div>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">4</span>
                    <div>
                      <p className="font-medium">Copiez vos clés</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Binance affiche deux valeurs :
                      </p>
                      <div className="mt-2 space-y-2">
                        <div className="flex items-center gap-2 text-sm bg-muted rounded-md p-2">
                          <Copy className="h-4 w-4 text-muted-foreground shrink-0" />
                          <div>
                            <span className="font-medium">API Key</span>
                            <span className="text-muted-foreground"> — à coller dans le champ "Clé API"</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 text-sm bg-muted rounded-md p-2">
                          <Copy className="h-4 w-4 text-muted-foreground shrink-0" />
                          <div>
                            <span className="font-medium">Secret Key</span>
                            <span className="text-muted-foreground"> — à coller dans le champ "Clé secrète"</span>
                          </div>
                        </div>
                      </div>
                      <p className="text-sm text-red-500 mt-2 font-medium">
                        La Secret Key n'est affichée qu'une seule fois ! Copiez-la immédiatement.
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">5</span>
                    <div>
                      <p className="font-medium">Collez-les dans InvestAI</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Cliquez sur <strong>"Connecter un exchange"</strong> en haut de cette page,
                        sélectionnez Binance, et collez vos deux clés.
                      </p>
                    </div>
                  </li>
                </ol>
              </div>
              <DialogFooter className="flex-col sm:flex-row gap-2">
                <Button variant="outline" onClick={() => setGuideExchange(null)}>
                  Fermer
                </Button>
                <Button onClick={() => { setGuideExchange(null); setShowAddKey(true); setSelectedExchange('binance') }}>
                  <Plus className="h-4 w-4 mr-2" />
                  Connecter Binance
                </Button>
              </DialogFooter>
            </>
          )}

          {guideExchange === 'kraken' && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-3">
                  <ExchangeLogo exchange="kraken" size={32} />
                  Créer une clé API sur Kraken
                </DialogTitle>
                <DialogDescription>
                  Suivez ces étapes pour générer une clé API en lecture seule.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-6 py-4">
                <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-4">
                  <div className="flex items-start gap-3">
                    <ShieldCheck className="h-5 w-5 text-yellow-500 mt-0.5 shrink-0" />
                    <div className="text-sm">
                      <p className="font-medium text-yellow-600 dark:text-yellow-400">Important : lecture seule</p>
                      <p className="text-muted-foreground mt-1">
                        Ne cochez <strong>jamais</strong> les permissions de trading ou de retrait.
                        InvestAI a uniquement besoin de <strong>lire</strong> vos soldes et votre historique.
                      </p>
                    </div>
                  </div>
                </div>

                <ol className="space-y-5">
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">1</span>
                    <div>
                      <p className="font-medium">Connectez-vous à votre compte Kraken</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Rendez-vous sur <a href="https://www.kraken.com/u/security/api" target="_blank" rel="noopener noreferrer" className="text-primary underline inline-flex items-center gap-1">kraken.com &gt; Sécurité &gt; API <ExternalLink className="h-3 w-3" /></a>
                      </p>
                      <p className="text-sm text-muted-foreground">
                        Ou : <strong>Paramètres</strong> (icône engrenage) &gt; <strong>Sécurité</strong> &gt; <strong>API</strong>
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">2</span>
                    <div>
                      <p className="font-medium">Créez une nouvelle clé API</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Cliquez sur <strong>"Add key"</strong> (ou "Ajouter une clé").
                        Donnez-lui un nom descriptif (ex: "InvestAI").
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">3</span>
                    <div>
                      <p className="font-medium">Configurez les permissions</p>
                      <p className="text-sm text-muted-foreground mt-1">Dans la section <strong>"Permissions"</strong>, cochez uniquement :</p>
                      <div className="mt-2 space-y-1.5">
                        <div className="flex items-center gap-2 text-sm">
                          <CheckCircle className="h-4 w-4 text-green-500" />
                          <span><strong>Query Funds</strong> — consulter vos soldes</span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <CheckCircle className="h-4 w-4 text-green-500" />
                          <span><strong>Query Open Orders & Trades</strong> — lire l'historique de trades</span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <CheckCircle className="h-4 w-4 text-green-500" />
                          <span><strong>Query Closed Orders & Trades</strong> — lire les ordres passés</span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <CheckCircle className="h-4 w-4 text-green-500" />
                          <span><strong>Query Ledger Entries</strong> — lire les mouvements de fonds</span>
                        </div>
                      </div>
                      <div className="mt-2 space-y-1.5">
                        <p className="text-sm text-muted-foreground">Ne cochez <strong>PAS</strong> :</p>
                        <div className="flex items-center gap-2 text-sm">
                          <XCircle className="h-4 w-4 text-red-500" />
                          <span className="text-muted-foreground">Create & Modify Orders</span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <XCircle className="h-4 w-4 text-red-500" />
                          <span className="text-muted-foreground">Cancel/Close Orders</span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <XCircle className="h-4 w-4 text-red-500" />
                          <span className="text-muted-foreground">Withdraw Funds</span>
                        </div>
                      </div>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">4</span>
                    <div>
                      <p className="font-medium">Générez et copiez vos clés</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Cliquez sur <strong>"Generate key"</strong>. Kraken affiche :
                      </p>
                      <div className="mt-2 space-y-2">
                        <div className="flex items-center gap-2 text-sm bg-muted rounded-md p-2">
                          <Copy className="h-4 w-4 text-muted-foreground shrink-0" />
                          <div>
                            <span className="font-medium">API Key</span>
                            <span className="text-muted-foreground"> — à coller dans le champ "Clé API"</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 text-sm bg-muted rounded-md p-2">
                          <Copy className="h-4 w-4 text-muted-foreground shrink-0" />
                          <div>
                            <span className="font-medium">Private Key</span>
                            <span className="text-muted-foreground"> — à coller dans le champ "Clé secrète"</span>
                          </div>
                        </div>
                      </div>
                      <p className="text-sm text-red-500 mt-2 font-medium">
                        La Private Key n'est affichée qu'une seule fois ! Copiez-la immédiatement.
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">5</span>
                    <div>
                      <p className="font-medium">Collez-les dans InvestAI</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Cliquez sur <strong>"Connecter un exchange"</strong> en haut de cette page,
                        sélectionnez Kraken, et collez vos deux clés.
                      </p>
                    </div>
                  </li>
                </ol>
              </div>
              <DialogFooter className="flex-col sm:flex-row gap-2">
                <Button variant="outline" onClick={() => setGuideExchange(null)}>
                  Fermer
                </Button>
                <Button onClick={() => { setGuideExchange(null); setShowAddKey(true); setSelectedExchange('kraken') }}>
                  <Plus className="h-4 w-4 mr-2" />
                  Connecter Kraken
                </Button>
              </DialogFooter>
            </>
          )}

          {guideExchange === 'coinbase' && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-3">
                  <ExchangeLogo exchange="coinbase" size={32} />
                  Créer une clé API sur Coinbase
                </DialogTitle>
                <DialogDescription>
                  Suivez ces étapes pour générer une clé API en lecture seule.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-6 py-4">
                <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-4">
                  <div className="flex items-start gap-3">
                    <ShieldCheck className="h-5 w-5 text-yellow-500 mt-0.5 shrink-0" />
                    <div className="text-sm">
                      <p className="font-medium text-yellow-600 dark:text-yellow-400">Important : lecture seule</p>
                      <p className="text-muted-foreground mt-1">
                        Ne cochez <strong>jamais</strong> les permissions de création, d'achat, de vente ou de retrait.
                        InvestAI a uniquement besoin de <strong>lire</strong> vos soldes et votre historique.
                      </p>
                    </div>
                  </div>
                </div>

                <ol className="space-y-5">
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">1</span>
                    <div>
                      <p className="font-medium">Allez dans Paramètres &gt; API</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Rendez-vous sur <a href="https://www.coinbase.com/settings/api" target="_blank" rel="noopener noreferrer" className="text-primary underline inline-flex items-center gap-1">coinbase.com/settings/api <ExternalLink className="h-3 w-3" /></a>
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">2</span>
                    <div>
                      <p className="font-medium">Créez une nouvelle clé API</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Cliquez sur <strong>"New API Key"</strong>.
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">3</span>
                    <div>
                      <p className="font-medium">Configurez les permissions</p>
                      <p className="text-sm text-muted-foreground mt-1">Cochez uniquement :</p>
                      <div className="mt-2 space-y-1.5">
                        <div className="flex items-center gap-2 text-sm">
                          <CheckCircle className="h-4 w-4 text-green-500" />
                          <span><strong>wallet:accounts:read</strong></span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <CheckCircle className="h-4 w-4 text-green-500" />
                          <span><strong>wallet:trades:read</strong></span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <CheckCircle className="h-4 w-4 text-green-500" />
                          <span><strong>wallet:transactions:read</strong></span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <CheckCircle className="h-4 w-4 text-green-500" />
                          <span><strong>wallet:deposits:read</strong></span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <CheckCircle className="h-4 w-4 text-green-500" />
                          <span><strong>wallet:withdrawals:read</strong></span>
                        </div>
                      </div>
                      <div className="mt-2 space-y-1.5">
                        <p className="text-sm text-muted-foreground">Ne cochez <strong>PAS</strong> :</p>
                        <div className="flex items-center gap-2 text-sm">
                          <XCircle className="h-4 w-4 text-red-500" />
                          <span className="text-muted-foreground">wallet:accounts:create</span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <XCircle className="h-4 w-4 text-red-500" />
                          <span className="text-muted-foreground">wallet:buys:create</span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <XCircle className="h-4 w-4 text-red-500" />
                          <span className="text-muted-foreground">wallet:sells:create</span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <XCircle className="h-4 w-4 text-red-500" />
                          <span className="text-muted-foreground">wallet:withdrawals:create</span>
                        </div>
                      </div>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">4</span>
                    <div>
                      <p className="font-medium">Copiez vos clés</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Coinbase affiche deux valeurs :
                      </p>
                      <div className="mt-2 space-y-2">
                        <div className="flex items-center gap-2 text-sm bg-muted rounded-md p-2">
                          <Copy className="h-4 w-4 text-muted-foreground shrink-0" />
                          <div>
                            <span className="font-medium">API Key</span>
                            <span className="text-muted-foreground"> — à coller dans le champ "Clé API"</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 text-sm bg-muted rounded-md p-2">
                          <Copy className="h-4 w-4 text-muted-foreground shrink-0" />
                          <div>
                            <span className="font-medium">API Secret</span>
                            <span className="text-muted-foreground"> — à coller dans le champ "Clé secrète"</span>
                          </div>
                        </div>
                      </div>
                      <p className="text-sm text-red-500 mt-2 font-medium">
                        L'API Secret n'est affiché qu'une seule fois ! Copiez-le immédiatement.
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">5</span>
                    <div>
                      <p className="font-medium">Collez-les dans InvestAI</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Cliquez sur <strong>"Connecter un exchange"</strong> en haut de cette page,
                        sélectionnez Coinbase, et collez vos deux clés.
                      </p>
                    </div>
                  </li>
                </ol>
              </div>
              <DialogFooter className="flex-col sm:flex-row gap-2">
                <Button variant="outline" onClick={() => setGuideExchange(null)}>
                  Fermer
                </Button>
                <Button onClick={() => { setGuideExchange(null); setShowAddKey(true); setSelectedExchange('coinbase') }}>
                  <Plus className="h-4 w-4 mr-2" />
                  Connecter Coinbase
                </Button>
              </DialogFooter>
            </>
          )}

          {guideExchange === 'cryptocom' && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-3">
                  <ExchangeLogo exchange="cryptocom" size={32} />
                  Créer une clé API sur Crypto.com
                </DialogTitle>
                <DialogDescription>
                  Suivez ces étapes pour générer une clé API en lecture seule.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-6 py-4">
                <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-4">
                  <div className="flex items-start gap-3">
                    <ShieldCheck className="h-5 w-5 text-yellow-500 mt-0.5 shrink-0" />
                    <div className="text-sm">
                      <p className="font-medium text-yellow-600 dark:text-yellow-400">Important : lecture seule</p>
                      <p className="text-muted-foreground mt-1">
                        Ne cochez <strong>jamais</strong> les permissions de trading ou de retrait.
                        InvestAI a uniquement besoin de <strong>lire</strong> vos soldes et votre historique.
                      </p>
                    </div>
                  </div>
                </div>

                <ol className="space-y-5">
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">1</span>
                    <div>
                      <p className="font-medium">Allez sur Crypto.com Exchange &gt; API Management</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Rendez-vous sur <a href="https://crypto.com/exchange/personal/api-management" target="_blank" rel="noopener noreferrer" className="text-primary underline inline-flex items-center gap-1">crypto.com/exchange &gt; API Management <ExternalLink className="h-3 w-3" /></a>
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">2</span>
                    <div>
                      <p className="font-medium">Créez une nouvelle clé API</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Cliquez sur <strong>"Create new API Key"</strong> et donnez-lui un nom (ex: "InvestAI").
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">3</span>
                    <div>
                      <p className="font-medium">Configurez les permissions</p>
                      <p className="text-sm text-muted-foreground mt-1">Cochez uniquement :</p>
                      <div className="mt-2 space-y-1.5">
                        <div className="flex items-center gap-2 text-sm">
                          <CheckCircle className="h-4 w-4 text-green-500" />
                          <span><strong>Read Only</strong></span>
                        </div>
                      </div>
                      <div className="mt-2 space-y-1.5">
                        <p className="text-sm text-muted-foreground">Ne cochez <strong>PAS</strong> :</p>
                        <div className="flex items-center gap-2 text-sm">
                          <XCircle className="h-4 w-4 text-red-500" />
                          <span className="text-muted-foreground">Can Trade</span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <XCircle className="h-4 w-4 text-red-500" />
                          <span className="text-muted-foreground">Can Withdraw</span>
                        </div>
                      </div>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">4</span>
                    <div>
                      <p className="font-medium">Copiez vos clés</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Crypto.com affiche deux valeurs :
                      </p>
                      <div className="mt-2 space-y-2">
                        <div className="flex items-center gap-2 text-sm bg-muted rounded-md p-2">
                          <Copy className="h-4 w-4 text-muted-foreground shrink-0" />
                          <div>
                            <span className="font-medium">API Key</span>
                            <span className="text-muted-foreground"> — à coller dans le champ "Clé API"</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 text-sm bg-muted rounded-md p-2">
                          <Copy className="h-4 w-4 text-muted-foreground shrink-0" />
                          <div>
                            <span className="font-medium">Secret Key</span>
                            <span className="text-muted-foreground"> — à coller dans le champ "Clé secrète"</span>
                          </div>
                        </div>
                      </div>
                      <p className="text-sm text-red-500 mt-2 font-medium">
                        La Secret Key n'est affichée qu'une seule fois ! Copiez-la immédiatement.
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">5</span>
                    <div>
                      <p className="font-medium">Collez-les dans InvestAI</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Cliquez sur <strong>"Connecter un exchange"</strong> en haut de cette page,
                        sélectionnez Crypto.com, et collez vos deux clés.
                      </p>
                    </div>
                  </li>
                </ol>
              </div>
              <DialogFooter className="flex-col sm:flex-row gap-2">
                <Button variant="outline" onClick={() => setGuideExchange(null)}>
                  Fermer
                </Button>
                <Button onClick={() => { setGuideExchange(null); setShowAddKey(true); setSelectedExchange('cryptocom') }}>
                  <Plus className="h-4 w-4 mr-2" />
                  Connecter Crypto.com
                </Button>
              </DialogFooter>
            </>
          )}

          {guideExchange === 'kucoin' && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-3">
                  <ExchangeLogo exchange="kucoin" size={32} />
                  Créer une clé API sur KuCoin
                </DialogTitle>
                <DialogDescription>
                  Suivez ces étapes pour générer une clé API en lecture seule.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-6 py-4">
                <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-4">
                  <div className="flex items-start gap-3">
                    <ShieldCheck className="h-5 w-5 text-yellow-500 mt-0.5 shrink-0" />
                    <div className="text-sm">
                      <p className="font-medium text-yellow-600 dark:text-yellow-400">Important : lecture seule</p>
                      <p className="text-muted-foreground mt-1">
                        Ne cochez <strong>jamais</strong> les permissions de trading ou de transfert.
                        InvestAI a uniquement besoin de <strong>lire</strong> vos soldes et votre historique.
                      </p>
                    </div>
                  </div>
                </div>

                <ol className="space-y-5">
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">1</span>
                    <div>
                      <p className="font-medium">Allez dans Account &gt; API Management</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Rendez-vous sur <a href="https://www.kucoin.com/account/api" target="_blank" rel="noopener noreferrer" className="text-primary underline inline-flex items-center gap-1">kucoin.com/account/api <ExternalLink className="h-3 w-3" /></a>
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">2</span>
                    <div>
                      <p className="font-medium">Créez une nouvelle clé API</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Cliquez sur <strong>"Create API"</strong>, choisissez un nom et définissez un <strong>passphrase</strong> (à retenir !).
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">3</span>
                    <div>
                      <p className="font-medium">Configurez les permissions</p>
                      <p className="text-sm text-muted-foreground mt-1">Cochez uniquement :</p>
                      <div className="mt-2 space-y-1.5">
                        <div className="flex items-center gap-2 text-sm">
                          <CheckCircle className="h-4 w-4 text-green-500" />
                          <span><strong>General</strong> — consulter vos soldes et historique</span>
                        </div>
                      </div>
                      <div className="mt-2 space-y-1.5">
                        <p className="text-sm text-muted-foreground">Ne cochez <strong>PAS</strong> :</p>
                        <div className="flex items-center gap-2 text-sm">
                          <XCircle className="h-4 w-4 text-red-500" />
                          <span className="text-muted-foreground">Trade</span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <XCircle className="h-4 w-4 text-red-500" />
                          <span className="text-muted-foreground">Transfer</span>
                        </div>
                      </div>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">4</span>
                    <div>
                      <p className="font-medium">Copiez vos clés et notez le passphrase</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        KuCoin affiche trois valeurs :
                      </p>
                      <div className="mt-2 space-y-2">
                        <div className="flex items-center gap-2 text-sm bg-muted rounded-md p-2">
                          <Copy className="h-4 w-4 text-muted-foreground shrink-0" />
                          <div>
                            <span className="font-medium">API Key</span>
                            <span className="text-muted-foreground"> — à coller dans le champ "Clé API"</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 text-sm bg-muted rounded-md p-2">
                          <Copy className="h-4 w-4 text-muted-foreground shrink-0" />
                          <div>
                            <span className="font-medium">Secret Key</span>
                            <span className="text-muted-foreground"> — à coller dans le champ "Clé secrète"</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 text-sm bg-muted rounded-md p-2">
                          <Copy className="h-4 w-4 text-muted-foreground shrink-0" />
                          <div>
                            <span className="font-medium">Passphrase</span>
                            <span className="text-muted-foreground"> — à coller dans le champ "Passphrase"</span>
                          </div>
                        </div>
                      </div>
                      <p className="text-sm text-red-500 mt-2 font-medium">
                        La Secret Key n'est affichée qu'une seule fois ! Copiez-la immédiatement. KuCoin nécessite 3 champs (incluez le passphrase !).
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">5</span>
                    <div>
                      <p className="font-medium">Collez les 3 valeurs dans InvestAI</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Cliquez sur <strong>"Connecter un exchange"</strong> en haut de cette page,
                        sélectionnez KuCoin, et collez vos trois valeurs (API Key, Secret, Passphrase).
                      </p>
                    </div>
                  </li>
                </ol>
              </div>
              <DialogFooter className="flex-col sm:flex-row gap-2">
                <Button variant="outline" onClick={() => setGuideExchange(null)}>
                  Fermer
                </Button>
                <Button onClick={() => { setGuideExchange(null); setShowAddKey(true); setSelectedExchange('kucoin') }}>
                  <Plus className="h-4 w-4 mr-2" />
                  Connecter KuCoin
                </Button>
              </DialogFooter>
            </>
          )}

          {guideExchange === 'bybit' && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-3">
                  <ExchangeLogo exchange="bybit" size={32} />
                  Créer une clé API sur Bybit
                </DialogTitle>
                <DialogDescription>
                  Suivez ces étapes pour générer une clé API en lecture seule.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-6 py-4">
                <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-4">
                  <div className="flex items-start gap-3">
                    <ShieldCheck className="h-5 w-5 text-yellow-500 mt-0.5 shrink-0" />
                    <div className="text-sm">
                      <p className="font-medium text-yellow-600 dark:text-yellow-400">Important : lecture seule</p>
                      <p className="text-muted-foreground mt-1">
                        Ne cochez <strong>jamais</strong> les permissions de trading, retrait ou transfert.
                        InvestAI a uniquement besoin de <strong>lire</strong> vos soldes et votre historique.
                      </p>
                    </div>
                  </div>
                </div>

                <ol className="space-y-5">
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">1</span>
                    <div>
                      <p className="font-medium">Allez dans Account & Security &gt; API Management</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Rendez-vous sur <a href="https://www.bybit.com/app/user/api-management" target="_blank" rel="noopener noreferrer" className="text-primary underline inline-flex items-center gap-1">bybit.com &gt; API Management <ExternalLink className="h-3 w-3" /></a>
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">2</span>
                    <div>
                      <p className="font-medium">Créez une nouvelle clé API</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Cliquez sur <strong>"Create New Key"</strong>, puis choisissez <strong>"System-generated API Keys"</strong>.
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">3</span>
                    <div>
                      <p className="font-medium">Configurez les permissions</p>
                      <p className="text-sm text-muted-foreground mt-1">Cochez uniquement :</p>
                      <div className="mt-2 space-y-1.5">
                        <div className="flex items-center gap-2 text-sm">
                          <CheckCircle className="h-4 w-4 text-green-500" />
                          <span><strong>Read-Only</strong></span>
                        </div>
                      </div>
                      <div className="mt-2 space-y-1.5">
                        <p className="text-sm text-muted-foreground">Ne cochez <strong>PAS</strong> :</p>
                        <div className="flex items-center gap-2 text-sm">
                          <XCircle className="h-4 w-4 text-red-500" />
                          <span className="text-muted-foreground">Trade</span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <XCircle className="h-4 w-4 text-red-500" />
                          <span className="text-muted-foreground">Withdraw</span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <XCircle className="h-4 w-4 text-red-500" />
                          <span className="text-muted-foreground">Transfer</span>
                        </div>
                      </div>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">4</span>
                    <div>
                      <p className="font-medium">Copiez vos clés</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Bybit affiche deux valeurs :
                      </p>
                      <div className="mt-2 space-y-2">
                        <div className="flex items-center gap-2 text-sm bg-muted rounded-md p-2">
                          <Copy className="h-4 w-4 text-muted-foreground shrink-0" />
                          <div>
                            <span className="font-medium">API Key</span>
                            <span className="text-muted-foreground"> — à coller dans le champ "Clé API"</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 text-sm bg-muted rounded-md p-2">
                          <Copy className="h-4 w-4 text-muted-foreground shrink-0" />
                          <div>
                            <span className="font-medium">Secret Key</span>
                            <span className="text-muted-foreground"> — à coller dans le champ "Clé secrète"</span>
                          </div>
                        </div>
                      </div>
                      <p className="text-sm text-red-500 mt-2 font-medium">
                        La Secret Key n'est affichée qu'une seule fois ! Copiez-la immédiatement.
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">5</span>
                    <div>
                      <p className="font-medium">Collez-les dans InvestAI</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Cliquez sur <strong>"Connecter un exchange"</strong> en haut de cette page,
                        sélectionnez Bybit, et collez vos deux clés.
                      </p>
                    </div>
                  </li>
                </ol>
              </div>
              <DialogFooter className="flex-col sm:flex-row gap-2">
                <Button variant="outline" onClick={() => setGuideExchange(null)}>
                  Fermer
                </Button>
                <Button onClick={() => { setGuideExchange(null); setShowAddKey(true); setSelectedExchange('bybit') }}>
                  <Plus className="h-4 w-4 mr-2" />
                  Connecter Bybit
                </Button>
              </DialogFooter>
            </>
          )}

          {guideExchange === 'okx' && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-3">
                  <ExchangeLogo exchange="okx" size={32} />
                  Créer une clé API sur OKX
                </DialogTitle>
                <DialogDescription>
                  Suivez ces étapes pour générer une clé API en lecture seule.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-6 py-4">
                <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-4">
                  <div className="flex items-start gap-3">
                    <ShieldCheck className="h-5 w-5 text-yellow-500 mt-0.5 shrink-0" />
                    <div className="text-sm">
                      <p className="font-medium text-yellow-600 dark:text-yellow-400">Important : lecture seule</p>
                      <p className="text-muted-foreground mt-1">
                        Ne cochez <strong>jamais</strong> les permissions de trading ou de retrait.
                        InvestAI a uniquement besoin de <strong>lire</strong> vos soldes et votre historique.
                      </p>
                    </div>
                  </div>
                </div>

                <ol className="space-y-5">
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">1</span>
                    <div>
                      <p className="font-medium">Allez dans Profile &gt; API Management</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Rendez-vous sur <a href="https://www.okx.com/account/my-api" target="_blank" rel="noopener noreferrer" className="text-primary underline inline-flex items-center gap-1">okx.com/account/my-api <ExternalLink className="h-3 w-3" /></a>
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">2</span>
                    <div>
                      <p className="font-medium">Créez une nouvelle clé API</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Cliquez sur <strong>"Create API Key"</strong>, choisissez un nom et définissez un <strong>passphrase</strong>.
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">3</span>
                    <div>
                      <p className="font-medium">Configurez les permissions</p>
                      <p className="text-sm text-muted-foreground mt-1">Cochez uniquement :</p>
                      <div className="mt-2 space-y-1.5">
                        <div className="flex items-center gap-2 text-sm">
                          <CheckCircle className="h-4 w-4 text-green-500" />
                          <span><strong>Read Only</strong></span>
                        </div>
                      </div>
                      <div className="mt-2 space-y-1.5">
                        <p className="text-sm text-muted-foreground">Ne cochez <strong>PAS</strong> :</p>
                        <div className="flex items-center gap-2 text-sm">
                          <XCircle className="h-4 w-4 text-red-500" />
                          <span className="text-muted-foreground">Trade</span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <XCircle className="h-4 w-4 text-red-500" />
                          <span className="text-muted-foreground">Withdraw</span>
                        </div>
                      </div>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">4</span>
                    <div>
                      <p className="font-medium">Copiez vos clés et notez le passphrase</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        OKX affiche trois valeurs :
                      </p>
                      <div className="mt-2 space-y-2">
                        <div className="flex items-center gap-2 text-sm bg-muted rounded-md p-2">
                          <Copy className="h-4 w-4 text-muted-foreground shrink-0" />
                          <div>
                            <span className="font-medium">API Key</span>
                            <span className="text-muted-foreground"> — à coller dans le champ "Clé API"</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 text-sm bg-muted rounded-md p-2">
                          <Copy className="h-4 w-4 text-muted-foreground shrink-0" />
                          <div>
                            <span className="font-medium">Secret Key</span>
                            <span className="text-muted-foreground"> — à coller dans le champ "Clé secrète"</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 text-sm bg-muted rounded-md p-2">
                          <Copy className="h-4 w-4 text-muted-foreground shrink-0" />
                          <div>
                            <span className="font-medium">Passphrase</span>
                            <span className="text-muted-foreground"> — à coller dans le champ "Passphrase"</span>
                          </div>
                        </div>
                      </div>
                      <p className="text-sm text-red-500 mt-2 font-medium">
                        La Secret Key n'est affichée qu'une seule fois ! Copiez-la immédiatement. OKX nécessite 3 champs (incluez le passphrase !).
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">5</span>
                    <div>
                      <p className="font-medium">Collez les 3 valeurs dans InvestAI</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Cliquez sur <strong>"Connecter un exchange"</strong> en haut de cette page,
                        sélectionnez OKX, et collez vos trois valeurs (API Key, Secret, Passphrase).
                      </p>
                    </div>
                  </li>
                </ol>
              </div>
              <DialogFooter className="flex-col sm:flex-row gap-2">
                <Button variant="outline" onClick={() => setGuideExchange(null)}>
                  Fermer
                </Button>
                <Button onClick={() => { setGuideExchange(null); setShowAddKey(true); setSelectedExchange('okx') }}>
                  <Plus className="h-4 w-4 mr-2" />
                  Connecter OKX
                </Button>
              </DialogFooter>
            </>
          )}

          {guideExchange === 'bitpanda' && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-3">
                  <ExchangeLogo exchange="bitpanda" size={32} />
                  Créer une clé API sur Bitpanda
                </DialogTitle>
                <DialogDescription>
                  Suivez ces étapes pour générer une clé API en lecture seule.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-6 py-4">
                <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-4">
                  <div className="flex items-start gap-3">
                    <ShieldCheck className="h-5 w-5 text-yellow-500 mt-0.5 shrink-0" />
                    <div className="text-sm">
                      <p className="font-medium text-yellow-600 dark:text-yellow-400">Important : lecture seule</p>
                      <p className="text-muted-foreground mt-1">
                        Ne cochez <strong>jamais</strong> les permissions de trading ou de retrait.
                        InvestAI a uniquement besoin de <strong>lire</strong> vos soldes et votre historique.
                      </p>
                    </div>
                  </div>
                </div>

                <ol className="space-y-5">
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">1</span>
                    <div>
                      <p className="font-medium">Allez dans Bitpanda Pro &gt; Settings &gt; API Keys</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Rendez-vous sur <a href="https://exchange.bitpanda.com/account/api" target="_blank" rel="noopener noreferrer" className="text-primary underline inline-flex items-center gap-1">exchange.bitpanda.com/account/api <ExternalLink className="h-3 w-3" /></a>
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">2</span>
                    <div>
                      <p className="font-medium">Générez une nouvelle clé</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Cliquez sur <strong>"Generate New Key"</strong>.
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">3</span>
                    <div>
                      <p className="font-medium">Configurez les permissions</p>
                      <p className="text-sm text-muted-foreground mt-1">Cochez uniquement :</p>
                      <div className="mt-2 space-y-1.5">
                        <div className="flex items-center gap-2 text-sm">
                          <CheckCircle className="h-4 w-4 text-green-500" />
                          <span><strong>Read</strong></span>
                        </div>
                      </div>
                      <div className="mt-2 space-y-1.5">
                        <p className="text-sm text-muted-foreground">Ne cochez <strong>PAS</strong> :</p>
                        <div className="flex items-center gap-2 text-sm">
                          <XCircle className="h-4 w-4 text-red-500" />
                          <span className="text-muted-foreground">Trade</span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <XCircle className="h-4 w-4 text-red-500" />
                          <span className="text-muted-foreground">Withdraw</span>
                        </div>
                      </div>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">4</span>
                    <div>
                      <p className="font-medium">Copiez votre clé API</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Bitpanda ne nécessite qu'une seule clé API (pas de clé secrète) :
                      </p>
                      <div className="mt-2 space-y-2">
                        <div className="flex items-center gap-2 text-sm bg-muted rounded-md p-2">
                          <Copy className="h-4 w-4 text-muted-foreground shrink-0" />
                          <div>
                            <span className="font-medium">API Key</span>
                            <span className="text-muted-foreground"> — à coller dans le champ "Clé API"</span>
                          </div>
                        </div>
                      </div>
                      <p className="text-sm text-red-500 mt-2 font-medium">
                        Bitpanda ne nécessite QU'UNE clé API, pas de secret. Seul le champ "Clé API" est requis.
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">5</span>
                    <div>
                      <p className="font-medium">Collez-la dans InvestAI</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Cliquez sur <strong>"Connecter un exchange"</strong> en haut de cette page,
                        sélectionnez Bitpanda, et collez votre clé API (seul champ requis).
                      </p>
                    </div>
                  </li>
                </ol>
              </div>
              <DialogFooter className="flex-col sm:flex-row gap-2">
                <Button variant="outline" onClick={() => setGuideExchange(null)}>
                  Fermer
                </Button>
                <Button onClick={() => { setGuideExchange(null); setShowAddKey(true); setSelectedExchange('bitpanda') }}>
                  <Plus className="h-4 w-4 mr-2" />
                  Connecter Bitpanda
                </Button>
              </DialogFooter>
            </>
          )}

          {guideExchange === 'bitstamp' && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-3">
                  <ExchangeLogo exchange="bitstamp" size={32} />
                  Créer une clé API sur Bitstamp
                </DialogTitle>
                <DialogDescription>
                  Suivez ces étapes pour générer une clé API en lecture seule.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-6 py-4">
                <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-4">
                  <div className="flex items-start gap-3">
                    <ShieldCheck className="h-5 w-5 text-yellow-500 mt-0.5 shrink-0" />
                    <div className="text-sm">
                      <p className="font-medium text-yellow-600 dark:text-yellow-400">Important : lecture seule</p>
                      <p className="text-muted-foreground mt-1">
                        Ne cochez <strong>jamais</strong> les permissions d'achat, de vente ou de retrait.
                        InvestAI a uniquement besoin de <strong>lire</strong> vos soldes et votre historique.
                      </p>
                    </div>
                  </div>
                </div>

                <ol className="space-y-5">
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">1</span>
                    <div>
                      <p className="font-medium">Allez dans Settings &gt; Security &gt; API Access</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Rendez-vous sur <a href="https://www.bitstamp.net/settings/api/" target="_blank" rel="noopener noreferrer" className="text-primary underline inline-flex items-center gap-1">bitstamp.net/settings/api <ExternalLink className="h-3 w-3" /></a>
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">2</span>
                    <div>
                      <p className="font-medium">Créez une nouvelle clé API</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Cliquez sur <strong>"Create New API Key"</strong>.
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">3</span>
                    <div>
                      <p className="font-medium">Configurez les permissions</p>
                      <p className="text-sm text-muted-foreground mt-1">Cochez uniquement :</p>
                      <div className="mt-2 space-y-1.5">
                        <div className="flex items-center gap-2 text-sm">
                          <CheckCircle className="h-4 w-4 text-green-500" />
                          <span><strong>Account balance</strong></span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <CheckCircle className="h-4 w-4 text-green-500" />
                          <span><strong>User transactions</strong></span>
                        </div>
                      </div>
                      <div className="mt-2 space-y-1.5">
                        <p className="text-sm text-muted-foreground">Ne cochez <strong>PAS</strong> :</p>
                        <div className="flex items-center gap-2 text-sm">
                          <XCircle className="h-4 w-4 text-red-500" />
                          <span className="text-muted-foreground">Buy/Sell</span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <XCircle className="h-4 w-4 text-red-500" />
                          <span className="text-muted-foreground">Withdrawals</span>
                        </div>
                      </div>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">4</span>
                    <div>
                      <p className="font-medium">Activez et copiez vos clés</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Activez la clé via la confirmation par email, puis copiez :
                      </p>
                      <div className="mt-2 space-y-2">
                        <div className="flex items-center gap-2 text-sm bg-muted rounded-md p-2">
                          <Copy className="h-4 w-4 text-muted-foreground shrink-0" />
                          <div>
                            <span className="font-medium">Key</span>
                            <span className="text-muted-foreground"> — à coller dans le champ "Clé API"</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 text-sm bg-muted rounded-md p-2">
                          <Copy className="h-4 w-4 text-muted-foreground shrink-0" />
                          <div>
                            <span className="font-medium">Secret</span>
                            <span className="text-muted-foreground"> — à coller dans le champ "Clé secrète"</span>
                          </div>
                        </div>
                      </div>
                      <p className="text-sm text-red-500 mt-2 font-medium">
                        La Secret n'est affichée qu'une seule fois ! Copiez-la immédiatement.
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">5</span>
                    <div>
                      <p className="font-medium">Collez-les dans InvestAI</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Cliquez sur <strong>"Connecter un exchange"</strong> en haut de cette page,
                        sélectionnez Bitstamp, et collez vos deux clés.
                      </p>
                    </div>
                  </li>
                </ol>
              </div>
              <DialogFooter className="flex-col sm:flex-row gap-2">
                <Button variant="outline" onClick={() => setGuideExchange(null)}>
                  Fermer
                </Button>
                <Button onClick={() => { setGuideExchange(null); setShowAddKey(true); setSelectedExchange('bitstamp') }}>
                  <Plus className="h-4 w-4 mr-2" />
                  Connecter Bitstamp
                </Button>
              </DialogFooter>
            </>
          )}

          {guideExchange === 'gateio' && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-3">
                  <ExchangeLogo exchange="gateio" size={32} />
                  Créer une clé API sur Gate.io
                </DialogTitle>
                <DialogDescription>
                  Suivez ces étapes pour générer une clé API en lecture seule.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-6 py-4">
                <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-4">
                  <div className="flex items-start gap-3">
                    <ShieldCheck className="h-5 w-5 text-yellow-500 mt-0.5 shrink-0" />
                    <div className="text-sm">
                      <p className="font-medium text-yellow-600 dark:text-yellow-400">Important : lecture seule</p>
                      <p className="text-muted-foreground mt-1">
                        Ne cochez <strong>jamais</strong> les permissions de trading ou de retrait.
                        InvestAI a uniquement besoin de <strong>lire</strong> vos soldes et votre historique.
                      </p>
                    </div>
                  </div>
                </div>

                <ol className="space-y-5">
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">1</span>
                    <div>
                      <p className="font-medium">Allez dans Account &gt; API Management</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Rendez-vous sur <a href="https://www.gate.io/myaccount/api_key_manage" target="_blank" rel="noopener noreferrer" className="text-primary underline inline-flex items-center gap-1">gate.io &gt; API Management <ExternalLink className="h-3 w-3" /></a>
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">2</span>
                    <div>
                      <p className="font-medium">Créez une nouvelle clé API</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Cliquez sur <strong>"Create API Key"</strong>.
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">3</span>
                    <div>
                      <p className="font-medium">Configurez les permissions</p>
                      <p className="text-sm text-muted-foreground mt-1">Cochez uniquement :</p>
                      <div className="mt-2 space-y-1.5">
                        <div className="flex items-center gap-2 text-sm">
                          <CheckCircle className="h-4 w-4 text-green-500" />
                          <span><strong>Spot Read-Only</strong></span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <CheckCircle className="h-4 w-4 text-green-500" />
                          <span><strong>Wallet Read-Only</strong></span>
                        </div>
                      </div>
                      <div className="mt-2 space-y-1.5">
                        <p className="text-sm text-muted-foreground">Ne cochez <strong>PAS</strong> :</p>
                        <div className="flex items-center gap-2 text-sm">
                          <XCircle className="h-4 w-4 text-red-500" />
                          <span className="text-muted-foreground">Spot Trade</span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <XCircle className="h-4 w-4 text-red-500" />
                          <span className="text-muted-foreground">Wallet Withdraw</span>
                        </div>
                      </div>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">4</span>
                    <div>
                      <p className="font-medium">Copiez vos clés</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Gate.io affiche deux valeurs :
                      </p>
                      <div className="mt-2 space-y-2">
                        <div className="flex items-center gap-2 text-sm bg-muted rounded-md p-2">
                          <Copy className="h-4 w-4 text-muted-foreground shrink-0" />
                          <div>
                            <span className="font-medium">API Key</span>
                            <span className="text-muted-foreground"> — à coller dans le champ "Clé API"</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 text-sm bg-muted rounded-md p-2">
                          <Copy className="h-4 w-4 text-muted-foreground shrink-0" />
                          <div>
                            <span className="font-medium">Secret Key</span>
                            <span className="text-muted-foreground"> — à coller dans le champ "Clé secrète"</span>
                          </div>
                        </div>
                      </div>
                      <p className="text-sm text-red-500 mt-2 font-medium">
                        La Secret Key n'est affichée qu'une seule fois ! Copiez-la immédiatement.
                      </p>
                    </div>
                  </li>
                  <li className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">5</span>
                    <div>
                      <p className="font-medium">Collez-les dans InvestAI</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Cliquez sur <strong>"Connecter un exchange"</strong> en haut de cette page,
                        sélectionnez Gate.io, et collez vos deux clés.
                      </p>
                    </div>
                  </li>
                </ol>
              </div>
              <DialogFooter className="flex-col sm:flex-row gap-2">
                <Button variant="outline" onClick={() => setGuideExchange(null)}>
                  Fermer
                </Button>
                <Button onClick={() => { setGuideExchange(null); setShowAddKey(true); setSelectedExchange('gateio') }}>
                  <Plus className="h-4 w-4 mr-2" />
                  Connecter Gate.io
                </Button>
              </DialogFooter>
            </>
          )}

          {guideExchange && !['binance', 'kraken', 'coinbase', 'cryptocom', 'kucoin', 'bybit', 'okx', 'bitpanda', 'bitstamp', 'gateio'].includes(guideExchange) && (
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
