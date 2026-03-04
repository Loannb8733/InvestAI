import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
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
            <Button onClick={() => onShowAddPortfolioChange(true)}>
              <Plus className="h-4 w-4 mr-2" />
              Créer un portefeuille
            </Button>
          </div>
        </CardContent>
      </Card>
      <AddPortfolioForm open={showAddPortfolio} onOpenChange={onShowAddPortfolioChange} />
    </div>
  )
}
