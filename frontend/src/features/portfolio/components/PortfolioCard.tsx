import { useState } from 'react'
import { History, Trash2, TrendingUp, Wallet } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import AddTransactionForm from '@/components/forms/AddTransactionForm'
import { formatCurrency, formatPercent } from '@/lib/utils'
import { arrow, gainClass } from '../format'
import { useDeleteAsset, useDeletePortfolio, useUpdateAssetExchange } from '../hooks'
import type { Portfolio, PortfolioHistory, PortfolioPerformance, Position, SparklineSeries } from '../types'
import AddAssetDialog from './AddAssetDialog'
import CashBalanceDialog from './CashBalanceDialog'
import ConfirmDeleteDialog from './ConfirmDeleteDialog'
import HistoryTab from './HistoryTab'
import PositionsTab from './PositionsTab'

interface PortfolioCardProps {
  portfolio: Portfolio
  performance: { data: PortfolioPerformance | undefined; isLoading: boolean }
  history: { data: PortfolioHistory | undefined; isLoading: boolean; isPlaceholderData: boolean }
  sparklines: Record<string, SparklineSeries> | undefined
  activeTab: string
  onTabChange: (tab: string) => void
  onDeleted: () => void
}

export default function PortfolioCard({ portfolio, performance, history, sparklines, activeTab, onTabChange, onDeleted }: PortfolioCardProps) {
  const [addingAsset, setAddingAsset] = useState(false)
  const [transactionFor, setTransactionFor] = useState<{ assetId: string; assetSymbol: string } | null>(null)
  const [cashOpen, setCashOpen] = useState(false)
  const [assetToDelete, setAssetToDelete] = useState<Position | null>(null)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const deleteAsset = useDeleteAsset(() => setAssetToDelete(null))
  const updateExchange = useUpdateAssetExchange()
  const deletePortfolio = useDeletePortfolio(
    () => {
      onDeleted()
      setConfirmingDelete(false)
    },
    () => setConfirmingDelete(false)
  )
  const totals = performance.data

  return (
    <>
      <Card elevation="raised">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-primary/20 flex items-center justify-center">
                <Wallet className="h-5 w-5 text-primary" />
              </div>
              <div>
                <CardTitle>{portfolio.name}</CardTitle>
                {portfolio.description && <p className="text-sm text-muted-foreground">{portfolio.description}</p>}
              </div>
            </div>
            <div className="flex items-center gap-4">
              {totals && (
                <div className="text-right">
                  <p className="text-2xl font-serif font-medium">{formatCurrency(totals.total_value)}</p>
                  <p className={`text-sm ${gainClass(totals.total_gain_loss)}`}>
                    {arrow(totals.total_gain_loss)} {formatCurrency(totals.total_gain_loss)} ({formatPercent(totals.total_gain_loss_percent)})
                  </p>
                </div>
              )}
              <Button variant="ghost" size="icon" onClick={() => setConfirmingDelete(true)} title="Supprimer le portefeuille">
                <Trash2 className="h-4 w-4 text-destructive" />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <Tabs value={activeTab} onValueChange={onTabChange} className="w-full">
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
            <TabsContent value="current">
              <PositionsTab
                performance={totals}
                loading={performance.isLoading}
                cashBalances={portfolio.cash_balances}
                sparklines={sparklines}
                onAddAsset={() => setAddingAsset(true)}
                onAddTransaction={(assetId, assetSymbol) => setTransactionFor({ assetId, assetSymbol })}
                onDeleteAsset={setAssetToDelete}
                onOpenCashBalance={() => setCashOpen(true)}
                onUpdateAssetExchange={(id, exchange) => updateExchange.mutate({ id, exchange })}
              />
            </TabsContent>
            <TabsContent value="history">
              <HistoryTab history={history.data} loading={history.isLoading} stale={history.isPlaceholderData} />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      {addingAsset && (
        <AddAssetDialog onOpenChange={() => setAddingAsset(false)} portfolioId={portfolio.id} portfolioName={portfolio.name} />
      )}
      {transactionFor && (
        <AddTransactionForm open onOpenChange={() => setTransactionFor(null)} assetId={transactionFor.assetId} assetSymbol={transactionFor.assetSymbol} />
      )}
      <CashBalanceDialog portfolioId={portfolio.id} cashBalances={portfolio.cash_balances} open={cashOpen} onOpenChange={setCashOpen} />

      <ConfirmDeleteDialog
        title="Supprimer cet actif ?"
        subject={assetToDelete?.symbol ?? null}
        question="Voulez-vous vraiment supprimer"
        consequence="Toutes les transactions associées seront également supprimées."
        pending={deleteAsset.isPending}
        onConfirm={() => assetToDelete && deleteAsset.mutate(assetToDelete.id)}
        onCancel={() => setAssetToDelete(null)}
      />
      <ConfirmDeleteDialog
        title="Supprimer ce portefeuille ?"
        subject={confirmingDelete ? portfolio.name : null}
        question="Voulez-vous vraiment supprimer le portefeuille"
        consequence="Tous les actifs et transactions associés seront également supprimés."
        pending={deletePortfolio.isPending}
        onConfirm={() => deletePortfolio.mutate(portfolio.id)}
        onCancel={() => setConfirmingDelete(false)}
      />
    </>
  )
}
