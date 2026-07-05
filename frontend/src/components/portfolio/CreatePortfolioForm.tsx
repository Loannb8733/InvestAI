import { Button } from '@/components/ui/button'
import EmptyState from '@/components/ui/empty-state'
import { Plus, Wallet } from 'lucide-react'
import AddPortfolioForm from '@/components/forms/AddPortfolioForm'

interface CreatePortfolioFormProps {
  showAddPortfolio: boolean
  onShowAddPortfolioChange: (open: boolean) => void
}

export default function CreatePortfolioForm({
  showAddPortfolio,
  onShowAddPortfolioChange,
}: CreatePortfolioFormProps) {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-serif font-medium">Portefeuille</h1>
      </div>
      <EmptyState
        icon={Wallet}
        title="Aucun portefeuille"
        description="Créez votre premier portefeuille pour commencer à suivre vos investissements."
        action={
          <Button onClick={() => onShowAddPortfolioChange(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Créer un portefeuille
          </Button>
        }
      />
      <AddPortfolioForm open={showAddPortfolio} onOpenChange={onShowAddPortfolioChange} />
    </div>
  )
}
