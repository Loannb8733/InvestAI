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
import { formatDate } from '@/lib/utils'
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
  }

  const fallbackColors: Record<string, string> = {
    binance: 'bg-[#F3BA2F]',
    kraken: 'bg-[#5741D9]',
  }

  const fallbackLabels: Record<string, string> = {
    binance: 'BN',
    kraken: 'KR',
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

  // Fetch supported exchanges
  const { data: exchanges } = useQuery<Exchange[]>({
    queryKey: ['exchanges'],
    queryFn: apiKeysApi.listExchanges,
  })

  // Fetch user's API keys
  const { data: apiKeys, isLoading } = useQuery<APIKey[]>({
    queryKey: ['apiKeys'],
    queryFn: apiKeysApi.list,
  })

  // Create API key mutation
  const createMutation = useMutation({
    mutationFn: apiKeysApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['apiKeys'] })
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
      queryClient.invalidateQueries({ queryKey: ['apiKeys'] })
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
      queryClient.invalidateQueries({ queryKey: ['apiKeys'] })
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
      queryClient.invalidateQueries({ queryKey: ['apiKeys'] })
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
      queryClient.invalidateQueries({ queryKey: ['apiKeys'] })
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
            Liste des exchanges que vous pouvez connecter à InvestAI.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {exchanges?.map((exchange) => {
              const connectedCount = getExchangeCount(exchange.id)
              return (
                <div
                  key={exchange.id}
                  className="flex items-start gap-3 p-4 rounded-lg border bg-muted/30 hover:bg-muted/50 transition-colors"
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
                  </div>
                </div>
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
        <DialogContent className="max-w-lg">
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
