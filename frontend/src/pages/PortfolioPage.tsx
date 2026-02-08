import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
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
import { formatCurrency, formatPercent } from '@/lib/utils'
import { invalidateAllFinancialData } from '@/lib/invalidate-queries'
import { portfoliosApi, assetsApi, dashboardApi, transactionsApi } from '@/services/api'
import AddPortfolioForm from '@/components/forms/AddPortfolioForm'
import AddAssetForm from '@/components/forms/AddAssetForm'
import AddTransactionForm from '@/components/forms/AddTransactionForm'
import ImportCSVForm from '@/components/forms/ImportCSVForm'
import CashBalanceForm from '@/components/forms/CashBalanceForm'
import { useToast } from '@/hooks/use-toast'
import {
  Plus,
  Wallet,
  Loader2,
  Trash2,
  ArrowRightLeft,
  Upload,
  Download,
  History,
  TrendingUp,
  PiggyBank,
  Banknote,
  AlertTriangle,
} from 'lucide-react'
import { AssetIconCompact } from '@/components/ui/asset-icon'

interface Portfolio {
  id: string
  name: string
  description?: string
  cash_balances?: Record<string, number>
}

interface AssetMetrics {
  id: string
  symbol: string
  name?: string
  asset_type: string
  quantity: number
  avg_buy_price: number
  current_price?: number
  current_value: number
  total_invested: number
  gain_loss: number
  gain_loss_percent: number
}

interface StablecoinEntry {
  id: string
  symbol: string
  quantity: number
  value: number
}

interface PortfolioMetrics {
  total_value: number
  total_invested: number
  total_gain_loss: number
  total_gain_loss_percent: number
  assets: AssetMetrics[]
  cash_from_stablecoins?: number
  stablecoins?: StablecoinEntry[]
  cash_from_fiat?: number
  fiat_assets?: StablecoinEntry[]
}

interface HistoricalAsset {
  id: string
  symbol: string
  name?: string
  asset_type: string
  current_quantity: number
  total_bought: number
  total_bought_value: number
  total_sold: number
  total_sold_value: number
  total_fees: number
  realized_gain: number
  first_transaction?: string
  last_transaction?: string
}

interface PortfolioHistory {
  total_invested_all_time: number
  total_sold: number
  total_fees: number
  realized_gains: number
  current_holdings_count: number
  sold_assets_count: number
  sold_assets: HistoricalAsset[]
}

export default function PortfolioPage() {
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const [showAddPortfolio, setShowAddPortfolio] = useState(false)
  const [showAddAsset, setShowAddAsset] = useState<{ portfolioId: string; portfolioName: string } | null>(null)
  const [showAddTransaction, setShowAddTransaction] = useState<{ assetId: string; assetSymbol: string } | null>(null)
  const [showImportCSV, setShowImportCSV] = useState(false)
  const [showCashBalance, setShowCashBalance] = useState(false)
  const [selectedPortfolio, setSelectedPortfolio] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState('current')
  const [deleteAsset, setDeleteAsset] = useState<AssetMetrics | null>(null)
  const [deletePortfolio, setDeletePortfolio] = useState<Portfolio | null>(null)

  // Fetch portfolios
  const { data: portfolios, isLoading: loadingPortfolios } = useQuery<Portfolio[]>({
    queryKey: ['portfolios'],
    queryFn: portfoliosApi.list,
  })

  // Fetch portfolio metrics (current holdings)
  const { data: portfolioMetrics, isLoading: loadingMetrics } = useQuery<PortfolioMetrics>({
    queryKey: ['portfolioMetrics', selectedPortfolio],
    queryFn: () => dashboardApi.getPortfolioMetrics(selectedPortfolio!),
    enabled: !!selectedPortfolio,
  })

  // Fetch portfolio history (including sold assets)
  const { data: portfolioHistory, isLoading: loadingHistory } = useQuery<PortfolioHistory>({
    queryKey: ['portfolioHistory', selectedPortfolio],
    queryFn: () => dashboardApi.getPortfolioHistory(selectedPortfolio!),
    enabled: !!selectedPortfolio && activeTab === 'history',
  })

  // Delete asset mutation
  const deleteAssetMutation = useMutation({
    mutationFn: assetsApi.delete,
    onSuccess: () => {
      invalidateAllFinancialData(queryClient)
      setDeleteAsset(null)
      toast({ title: 'Actif et transactions supprimés' })
    },
    onError: () => {
      setDeleteAsset(null)
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de supprimer l\'actif' })
    },
  })

  // Delete portfolio mutation
  const deletePortfolioMutation = useMutation({
    mutationFn: portfoliosApi.delete,
    onSuccess: () => {
      invalidateAllFinancialData(queryClient)
      setSelectedPortfolio(null)
      setDeletePortfolio(null)
      toast({ title: 'Portefeuille supprimé' })
    },
    onError: () => {
      setDeletePortfolio(null)
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de supprimer le portefeuille' })
    },
  })

  // Auto-select first portfolio
  if (portfolios && portfolios.length > 0 && !selectedPortfolio) {
    setSelectedPortfolio(portfolios[0].id)
  }

  if (loadingPortfolios) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  // Empty state
  if (!portfolios || portfolios.length === 0) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-3xl font-bold">Portefeuille</h1>
        </div>
        <Card>
          <CardContent className="py-12">
            <div className="text-center space-y-4">
              <Wallet className="h-16 w-16 mx-auto text-muted-foreground" />
              <h2 className="text-xl font-semibold">Aucun portefeuille</h2>
              <p className="text-muted-foreground max-w-md mx-auto">
                Créez votre premier portefeuille pour commencer à suivre vos investissements.
              </p>
              <Button onClick={() => setShowAddPortfolio(true)}>
                <Plus className="h-4 w-4 mr-2" />
                Créer un portefeuille
              </Button>
            </div>
          </CardContent>
        </Card>
        <AddPortfolioForm open={showAddPortfolio} onOpenChange={setShowAddPortfolio} />
      </div>
    )
  }

  const currentPortfolio = portfolios.find((p) => p.id === selectedPortfolio)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Portefeuille</h1>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setShowImportCSV(true)}>
            <Upload className="h-4 w-4 mr-2" />
            Importer CSV
          </Button>
          <Button
            variant="outline"
            onClick={async () => {
              try {
                const blob = await transactionsApi.exportCSV(selectedPortfolio || undefined)
                const url = window.URL.createObjectURL(blob)
                const a = document.createElement('a')
                a.href = url
                a.download = 'transactions_export.csv'
                a.click()
                window.URL.revokeObjectURL(url)
                toast({ title: 'Export réussi', description: 'Le fichier CSV a été téléchargé.' })
              } catch {
                toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible d\'exporter les transactions.' })
              }
            }}
          >
            <Download className="h-4 w-4 mr-2" />
            Exporter CSV
          </Button>
          <Button onClick={() => setShowAddPortfolio(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Nouveau portefeuille
          </Button>
        </div>
      </div>

      {/* Portfolio selector */}
      <div className="flex gap-2 flex-wrap">
        {portfolios.map((portfolio) => (
          <Button
            key={portfolio.id}
            variant={selectedPortfolio === portfolio.id ? 'default' : 'outline'}
            onClick={() => setSelectedPortfolio(portfolio.id)}
          >
            {portfolio.name}
          </Button>
        ))}
      </div>

      {/* Selected portfolio */}
      {currentPortfolio && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-full bg-primary/20 flex items-center justify-center">
                  <Wallet className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <CardTitle>{currentPortfolio.name}</CardTitle>
                  {currentPortfolio.description && (
                    <p className="text-sm text-muted-foreground">{currentPortfolio.description}</p>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-4">
                {portfolioMetrics && (
                  <div className="text-right">
                    <p className="text-2xl font-bold">{formatCurrency(portfolioMetrics.total_value)}</p>
                    <p className={`text-sm ${portfolioMetrics.total_gain_loss >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                      {formatCurrency(portfolioMetrics.total_gain_loss)} ({formatPercent(portfolioMetrics.total_gain_loss_percent)})
                    </p>
                  </div>
                )}
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setDeletePortfolio(currentPortfolio)}
                  title="Supprimer le portefeuille"
                >
                  <Trash2 className="h-4 w-4 text-destructive" />
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
              <TabsList className="grid w-full grid-cols-2 mb-4">
                <TabsTrigger value="current" className="flex items-center gap-2">
                  <TrendingUp className="h-4 w-4" />
                  Actifs actuels
                </TabsTrigger>
                <TabsTrigger value="history" className="flex items-center gap-2">
                  <History className="h-4 w-4" />
                  Historique
                </TabsTrigger>
              </TabsList>

              {/* Current Holdings Tab */}
              <TabsContent value="current">
                {/* Cash + Stablecoins cards side by side */}
                <div className="grid grid-cols-2 gap-4 mb-4">
                  {/* Cash disponible card */}
                  {(() => {
                    const manualCash = Object.values(currentPortfolio?.cash_balances || {}).reduce((sum, val) => sum + val, 0)
                    const fiatCash = portfolioMetrics?.cash_from_fiat || 0
                    const totalCash = manualCash + fiatCash
                    const cashEntries = Object.entries(currentPortfolio?.cash_balances || {})
                    const fiatEntries = portfolioMetrics?.fiat_assets || []

                    return (
                      <Card
                        className="cursor-pointer hover:bg-muted/50 transition-colors"
                        onClick={() => setShowCashBalance(true)}
                      >
                        <CardContent className="py-4">
                          <div className="flex items-center gap-3">
                            <div className="h-10 w-10 rounded-full bg-emerald-500/20 flex items-center justify-center shrink-0">
                              <Banknote className="h-5 w-5 text-emerald-500" />
                            </div>
                            <div className="min-w-0">
                              <p className="text-sm text-muted-foreground">Cash disponible</p>
                              <p className="text-xl font-bold">{formatCurrency(totalCash)}</p>
                              {(cashEntries.length > 0 || fiatEntries.length > 0) && (
                                <div className="text-xs text-muted-foreground mt-1">
                                  {cashEntries.map(([ex, amt]) => (
                                    <span key={ex} className="mr-2">{ex}: {formatCurrency(amt)}</span>
                                  ))}
                                  {fiatEntries.map((f) => (
                                    <span key={f.id} className="mr-2">{f.symbol}: {formatCurrency(f.value)}</span>
                                  ))}
                                </div>
                              )}
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    )
                  })()}

                  {/* Stablecoins card */}
                  <Card>
                    <CardContent className="py-4">
                      <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-full bg-blue-500/20 flex items-center justify-center shrink-0">
                          <span className="text-blue-500 font-bold text-sm">$</span>
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm text-muted-foreground">Stablecoins</p>
                          <p className="text-xl font-bold">
                            {formatCurrency(portfolioMetrics?.cash_from_stablecoins || 0)}
                          </p>
                          {(portfolioMetrics?.stablecoins?.length ?? 0) > 0 && (
                            <div className="text-xs text-muted-foreground mt-1">
                              {portfolioMetrics!.stablecoins!.map((sc) => (
                                <span key={sc.id} className="mr-2">{sc.symbol}: {sc.quantity.toFixed(2)}</span>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </div>

                {loadingMetrics ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="h-6 w-6 animate-spin text-primary" />
                  </div>
                ) : portfolioMetrics && portfolioMetrics.assets.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b">
                          <th className="text-center py-2 text-sm font-medium text-muted-foreground">Actif</th>
                          <th className="text-center py-2 text-sm font-medium text-muted-foreground">Quantité</th>
                          <th className="text-center py-2 text-sm font-medium text-muted-foreground">PRA</th>
                          <th className="text-center py-2 text-sm font-medium text-muted-foreground">Prix actuel</th>
                          <th className="text-center py-2 text-sm font-medium text-muted-foreground">Valeur</th>
                          <th className="text-center py-2 text-sm font-medium text-muted-foreground">+/- Value</th>
                          <th className="text-center py-2 text-sm font-medium text-muted-foreground">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {portfolioMetrics.assets.map((asset) => (
                          <tr key={asset.id} className="border-b last:border-0">
                            <td className="py-3 text-center">
                              <div className="flex justify-center">
                                <AssetIconCompact
                                  symbol={asset.symbol}
                                  name={asset.name}
                                  assetType={asset.asset_type}
                                  size={36}
                                />
                              </div>
                            </td>
                            <td className="text-center py-3">{asset.quantity.toFixed(asset.quantity < 1 ? 8 : 2)}</td>
                            <td className="text-center py-3 text-muted-foreground">
                              {asset.avg_buy_price > 0 ? formatCurrency(asset.avg_buy_price) : '-'}
                            </td>
                            <td className="text-center py-3">
                              {asset.current_price ? formatCurrency(asset.current_price) : '-'}
                            </td>
                            <td className="text-center py-3 font-medium">{formatCurrency(asset.current_value)}</td>
                            <td className={`text-center py-3 ${asset.gain_loss >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                              <div>
                                <p>{formatCurrency(asset.gain_loss)}</p>
                                <p className="text-xs">
                                  {asset.avg_buy_price > 0 && asset.current_price
                                    ? `${((asset.current_price - asset.avg_buy_price) / asset.avg_buy_price * 100).toFixed(2)}%`
                                    : formatPercent(asset.gain_loss_percent)}
                                </p>
                              </div>
                            </td>
                            <td className="text-center py-3">
                              <div className="flex justify-center gap-1">
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  onClick={() => setShowAddTransaction({ assetId: asset.id, assetSymbol: asset.symbol })}
                                  title="Ajouter une transaction"
                                >
                                  <ArrowRightLeft className="h-4 w-4" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  onClick={() => setDeleteAsset(asset)}
                                  title="Supprimer"
                                >
                                  <Trash2 className="h-4 w-4 text-destructive" />
                                </Button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    Aucun actif dans ce portefeuille
                  </div>
                )}
                <div className="mt-4">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowAddAsset({ portfolioId: currentPortfolio.id, portfolioName: currentPortfolio.name })}
                  >
                    <Plus className="h-4 w-4 mr-1" />
                    Ajouter un actif
                  </Button>
                </div>
              </TabsContent>

              {/* History Tab */}
              <TabsContent value="history">
                {loadingHistory ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="h-6 w-6 animate-spin text-primary" />
                  </div>
                ) : portfolioHistory ? (
                  <div className="space-y-6">
                    {/* Summary cards */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <Card>
                        <CardContent className="pt-6">
                          <div className="flex items-center gap-3">
                            <div className="h-10 w-10 rounded-full bg-blue-500/20 flex items-center justify-center">
                              <PiggyBank className="h-5 w-5 text-blue-500" />
                            </div>
                            <div>
                              <p className="text-sm text-muted-foreground">Total investi (historique)</p>
                              <p className="text-xl font-bold">{formatCurrency(portfolioHistory.total_invested_all_time)}</p>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                      <Card>
                        <CardContent className="pt-6">
                          <div className="flex items-center gap-3">
                            <div className="h-10 w-10 rounded-full bg-green-500/20 flex items-center justify-center">
                              <TrendingUp className="h-5 w-5 text-green-500" />
                            </div>
                            <div>
                              <p className="text-sm text-muted-foreground">Total vendu</p>
                              <p className="text-xl font-bold">{formatCurrency(portfolioHistory.total_sold)}</p>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                      <Card>
                        <CardContent className="pt-6">
                          <div className="flex items-center gap-3">
                            <div className="h-10 w-10 rounded-full bg-orange-500/20 flex items-center justify-center">
                              <History className="h-5 w-5 text-orange-500" />
                            </div>
                            <div>
                              <p className="text-sm text-muted-foreground">Frais totaux</p>
                              <p className="text-xl font-bold">{formatCurrency(portfolioHistory.total_fees)}</p>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    </div>

                    {/* Sold assets table */}
                    {portfolioHistory.sold_assets.length > 0 ? (
                      <div>
                        <h3 className="text-lg font-semibold mb-3">Actifs vendus ({portfolioHistory.sold_assets_count})</h3>
                        <div className="overflow-x-auto">
                          <table className="w-full">
                            <thead>
                              <tr className="border-b">
                                <th className="text-center py-2 text-sm font-medium text-muted-foreground">Actif</th>
                                <th className="text-center py-2 text-sm font-medium text-muted-foreground">Qté achetée</th>
                                <th className="text-center py-2 text-sm font-medium text-muted-foreground">Total investi</th>
                                <th className="text-center py-2 text-sm font-medium text-muted-foreground">Qté vendue</th>
                                <th className="text-center py-2 text-sm font-medium text-muted-foreground">Total vendu</th>
                                <th className="text-center py-2 text-sm font-medium text-muted-foreground">+/- Réalisé</th>
                              </tr>
                            </thead>
                            <tbody>
                              {portfolioHistory.sold_assets.map((asset) => (
                                <tr key={asset.id} className="border-b last:border-0">
                                  <td className="py-3 text-center">
                                    <div className="flex justify-center">
                                      <AssetIconCompact
                                        symbol={asset.symbol}
                                        name={asset.name}
                                        assetType={asset.asset_type}
                                        size={36}
                                      />
                                    </div>
                                  </td>
                                  <td className="text-center py-3">{asset.total_bought.toFixed(asset.total_bought < 1 ? 8 : 2)}</td>
                                  <td className="text-center py-3">{formatCurrency(asset.total_bought_value)}</td>
                                  <td className="text-center py-3">{asset.total_sold.toFixed(asset.total_sold < 1 ? 8 : 2)}</td>
                                  <td className="text-center py-3">{formatCurrency(asset.total_sold_value)}</td>
                                  <td className={`text-center py-3 ${asset.realized_gain >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                                    {formatCurrency(asset.realized_gain)}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    ) : (
                      <div className="text-center py-8 text-muted-foreground">
                        Aucun actif vendu
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    Aucune donnée historique
                  </div>
                )}
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      )}

      {/* Dialogs */}
      <AddPortfolioForm open={showAddPortfolio} onOpenChange={setShowAddPortfolio} />

      {showAddAsset && (
        <AddAssetForm
          open={true}
          onOpenChange={() => setShowAddAsset(null)}
          portfolioId={showAddAsset.portfolioId}
          portfolioName={showAddAsset.portfolioName}
        />
      )}

      {showAddTransaction && (
        <AddTransactionForm
          open={true}
          onOpenChange={() => setShowAddTransaction(null)}
          assetId={showAddTransaction.assetId}
          assetSymbol={showAddTransaction.assetSymbol}
        />
      )}

      <ImportCSVForm
        open={showImportCSV}
        onOpenChange={setShowImportCSV}
        portfolioId={selectedPortfolio || undefined}
        onSuccess={() => {
          setShowImportCSV(false)
          queryClient.invalidateQueries({ queryKey: ['portfolioMetrics'] })
          queryClient.invalidateQueries({ queryKey: ['portfolioHistory'] })
        }}
      />

      {currentPortfolio && (
        <CashBalanceForm
          portfolioId={currentPortfolio.id}
          cashBalances={currentPortfolio.cash_balances || {}}
          open={showCashBalance}
          onOpenChange={setShowCashBalance}
        />
      )}

      {/* Delete Asset Confirmation */}
      <AlertDialog open={deleteAsset !== null} onOpenChange={(open) => !open && setDeleteAsset(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-destructive" />
              Supprimer cet actif ?
            </AlertDialogTitle>
            <AlertDialogDescription>
              {deleteAsset && (
                <>
                  Voulez-vous vraiment supprimer <strong>{deleteAsset.symbol}</strong> ?
                  <br /><br />
                  <span className="text-destructive font-medium">
                    Toutes les transactions associées seront également supprimées.
                  </span>
                  <br />
                  Cette action est irréversible.
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annuler</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive hover:bg-destructive/90"
              onClick={() => deleteAsset && deleteAssetMutation.mutate(deleteAsset.id)}
              disabled={deleteAssetMutation.isPending}
            >
              {deleteAssetMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : null}
              Supprimer
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete Portfolio Confirmation */}
      <AlertDialog open={deletePortfolio !== null} onOpenChange={(open) => !open && setDeletePortfolio(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-destructive" />
              Supprimer ce portefeuille ?
            </AlertDialogTitle>
            <AlertDialogDescription>
              {deletePortfolio && (
                <>
                  Voulez-vous vraiment supprimer le portefeuille <strong>{deletePortfolio.name}</strong> ?
                  <br /><br />
                  <span className="text-destructive font-medium">
                    Tous les actifs et transactions associés seront également supprimés.
                  </span>
                  <br />
                  Cette action est irréversible.
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annuler</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive hover:bg-destructive/90"
              onClick={() => deletePortfolio && deletePortfolioMutation.mutate(deletePortfolio.id)}
              disabled={deletePortfolioMutation.isPending}
            >
              {deletePortfolioMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : null}
              Supprimer
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
