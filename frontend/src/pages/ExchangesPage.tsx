import { useState } from 'react'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageSkeleton } from '@/components/ui/page-skeleton'
import QueryErrorState from '@/components/ui/query-error-state'
import ColdWalletsManager from '@/features/exchanges/components/ColdWalletsManager'
import ConnectDialog from '@/features/exchanges/components/ConnectDialog'
import ConnectionList from '@/features/exchanges/components/ConnectionList'
import DeleteConnectionDialog from '@/features/exchanges/components/DeleteConnectionDialog'
import GuideDialog from '@/features/exchanges/components/GuideDialog'
import HowItWorksCard from '@/features/exchanges/components/HowItWorksCard'
import ReconciliationCard from '@/features/exchanges/components/ReconciliationCard'
import RenameDialog from '@/features/exchanges/components/RenameDialog'
import SupportedExchangesCard from '@/features/exchanges/components/SupportedExchangesCard'
import TestResultDialog from '@/features/exchanges/components/TestResultDialog'
import WalletsCard from '@/features/exchanges/components/WalletsCard'
import { guideFor } from '@/features/exchanges/guides/registry'
import { useApiKeys, useCreateKey, useDeleteKey, useExchanges } from '@/features/exchanges/hooks'
import { useKeyActions } from '@/features/exchanges/keyActions'
import { useReconciliation } from '@/features/exchanges/reconciliation'
import type { ApiKey, TestResult } from '@/features/exchanges/types'

const DESCRIPTION = 'Connectez vos exchanges pour synchroniser automatiquement vos positions.'

export default function ExchangesPage() {
  const exchanges = useExchanges()
  const apiKeys = useApiKeys()
  const reconciliation = useReconciliation()
  const [connecting, setConnecting] = useState(false)
  const [connectExchange, setConnectExchange] = useState('')
  const [guideExchange, setGuideExchange] = useState<string | null>(null)
  const [renaming, setRenaming] = useState<ApiKey | null>(null)
  const [deleting, setDeleting] = useState<ApiKey | null>(null)
  const [testResult, setTestResult] = useState<TestResult | null>(null)
  const create = useCreateKey(() => {
    setConnecting(false)
    setConnectExchange('')
  })
  const remove = useDeleteKey()
  const { actions, update } = useKeyActions({
    onTested: setTestResult,
    onSaved: () => setRenaming(null),
    onTaskCompleted: reconciliation.checkAfterTask,
  })
  const nameOf = (exchangeId: string) =>
    exchanges.data?.find((exchange) => exchange.id === exchangeId)?.name || guideFor(exchangeId)?.name || exchangeId

  if (apiKeys.isLoading) {
    return <PageSkeleton titre="Exchanges" description={DESCRIPTION} niveauTitre={2} forme="cartes" action />
  }

  if (apiKeys.isError) {
    return (
      <QueryErrorState
        error={apiKeys.error}
        onRetry={apiKeys.refetch}
        busy={apiKeys.isFetching}
        title="Impossible de charger vos clés API"
      />
    )
  }

  const keys = apiKeys.data ?? []

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-3xl font-serif font-medium">Exchanges</h2>
          <p className="text-muted-foreground">{DESCRIPTION}</p>
        </div>
        <Button onClick={() => setConnecting(true)} className="w-full sm:w-auto">
          <Plus className="h-4 w-4 mr-2" />
          Connecter un exchange
        </Button>
      </div>

      <ConnectionList
        apiKeys={keys}
        nameOf={nameOf}
        actions={actions}
        onConnect={() => setConnecting(true)}
        onRename={setRenaming}
        onDelete={setDeleting}
      />
      <WalletsCard />
      <ColdWalletsManager />
      <HowItWorksCard />
      <SupportedExchangesCard
        exchanges={exchanges.data}
        apiKeys={keys}
        failed={exchanges.isError}
        retrying={exchanges.isFetching}
        onRetry={exchanges.refetch}
        onGuide={setGuideExchange}
      />
      <ReconciliationCard reconciliation={reconciliation} />

      <ConnectDialog
        open={connecting}
        onOpenChange={setConnecting}
        exchanges={exchanges.data}
        selected={connectExchange}
        onSelect={setConnectExchange}
        pending={create.isPending}
        onSubmit={(body) => create.mutate(body)}
      />
      <TestResultDialog result={testResult} onClose={() => setTestResult(null)} />
      <GuideDialog
        exchangeId={guideExchange}
        exchanges={exchanges.data}
        onClose={() => setGuideExchange(null)}
        onConnect={(exchangeId) => {
          setGuideExchange(null)
          setConnecting(true)
          setConnectExchange(exchangeId)
        }}
      />
      <RenameDialog
        target={renaming}
        exchangeName={nameOf}
        saving={update.isPending}
        onSave={(id, label) => update.mutate({ id, data: { label } })}
        onClose={() => setRenaming(null)}
      />
      <DeleteConnectionDialog
        target={deleting}
        exchangeName={nameOf}
        onConfirm={() => {
          if (deleting) remove.mutate(deleting.id)
          setDeleting(null)
        }}
        onClose={() => setDeleting(null)}
      />
    </div>
  )
}
