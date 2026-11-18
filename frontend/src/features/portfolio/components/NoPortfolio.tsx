import { useState } from 'react'
import { Plus, Wallet } from 'lucide-react'
import { Button } from '@/components/ui/button'
import EmptyState from '@/components/ui/empty-state'
import AddPortfolioDialog from './AddPortfolioDialog'

export default function NoPortfolio() {
  const [adding, setAdding] = useState(false)
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-serif font-medium">Portefeuille</h2>
      </div>
      <EmptyState
        icon={Wallet}
        title="Aucun portefeuille"
        description="Créez votre premier portefeuille pour commencer à suivre vos investissements."
        action={
          <Button onClick={() => setAdding(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Créer un portefeuille
          </Button>
        }
      />
      <AddPortfolioDialog open={adding} onOpenChange={setAdding} />
    </div>
  )
}
