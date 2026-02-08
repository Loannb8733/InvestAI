import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { formatCurrency } from '@/lib/utils'
import { goalsApi } from '@/services/api'
import { useToast } from '@/hooks/use-toast'
import {
  Plus,
  Target,
  Loader2,
  Trash2,
  RefreshCw,
  Calendar,
  TrendingUp,
  CheckCircle2,
} from 'lucide-react'

interface Goal {
  id: string
  name: string
  target_amount: number
  current_amount: number
  currency: string
  target_date: string | null
  status: string
  icon: string
  color: string
  notes: string | null
  progress_percent: number
  days_remaining: number | null
  monthly_needed: number | null
  created_at: string
}

export default function GoalsPage() {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [name, setName] = useState('')
  const [targetAmount, setTargetAmount] = useState('')
  const [targetDate, setTargetDate] = useState('')
  const [color, setColor] = useState('#6366f1')

  const { data: goals = [], isLoading } = useQuery<Goal[]>({
    queryKey: ['goals'],
    queryFn: goalsApi.list,
  })

  const createMutation = useMutation({
    mutationFn: goalsApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals'] })
      toast({ title: 'Objectif cree' })
      setShowAdd(false)
      setName('')
      setTargetAmount('')
      setTargetDate('')
    },
  })

  const syncMutation = useMutation({
    mutationFn: (id: string) => goalsApi.sync(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals'] })
      toast({ title: 'Objectif synchronise avec le portefeuille' })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => goalsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals'] })
      toast({ title: 'Objectif supprime' })
    },
  })

  const handleCreate = () => {
    if (!name || !targetAmount) return
    createMutation.mutate({
      name,
      target_amount: parseFloat(targetAmount),
      target_date: targetDate || undefined,
      color,
    })
  }

  const activeGoals = goals.filter((g) => g.status === 'active')
  const reachedGoals = goals.filter((g) => g.status === 'reached')

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Objectifs financiers</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Definissez vos objectifs et suivez votre progression
          </p>
        </div>
        <Dialog open={showAdd} onOpenChange={setShowAdd}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="h-4 w-4 mr-2" />
              Nouvel objectif
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Nouvel objectif</DialogTitle>
              <DialogDescription>Definissez un objectif financier a atteindre</DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <Label>Nom</Label>
                <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ex: 100k€ de patrimoine" />
              </div>
              <div>
                <Label>Montant cible (€)</Label>
                <Input type="number" value={targetAmount} onChange={(e) => setTargetAmount(e.target.value)} placeholder="100000" />
              </div>
              <div>
                <Label>Date cible (optionnel)</Label>
                <Input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
              </div>
              <div>
                <Label>Couleur</Label>
                <Input type="color" value={color} onChange={(e) => setColor(e.target.value)} className="h-10 w-20" />
              </div>
              <Button onClick={handleCreate} disabled={createMutation.isPending} className="w-full">
                {createMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
                Creer
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {goals.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Target className="h-16 w-16 mx-auto text-muted-foreground mb-4" />
            <h2 className="text-xl font-semibold">Aucun objectif</h2>
            <p className="text-muted-foreground mt-2">Creez votre premier objectif financier pour suivre votre progression.</p>
          </CardContent>
        </Card>
      ) : (
        <>
          {activeGoals.length > 0 && (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {activeGoals.map((goal) => (
                <Card key={goal.id}>
                  <CardHeader className="pb-2">
                    <CardTitle className="flex items-center justify-between text-base">
                      <span className="flex items-center gap-2">
                        <div className="h-3 w-3 rounded-full" style={{ backgroundColor: goal.color }} />
                        {goal.name}
                      </span>
                      <div className="flex gap-1">
                        <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => syncMutation.mutate(goal.id)}>
                          <RefreshCw className={`h-3 w-3 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
                        </Button>
                        <Button variant="ghost" size="sm" className="h-7 w-7 p-0 text-destructive" onClick={() => deleteMutation.mutate(goal.id)}>
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div>
                      <div className="flex justify-between text-sm mb-1">
                        <span>{formatCurrency(goal.current_amount)}</span>
                        <span className="text-muted-foreground">{formatCurrency(goal.target_amount)}</span>
                      </div>
                      <div className="h-3 bg-muted rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{ width: `${Math.min(goal.progress_percent, 100)}%`, backgroundColor: goal.color }}
                        />
                      </div>
                      <p className="text-xs text-muted-foreground mt-1">{goal.progress_percent}%</p>
                    </div>
                    <div className="flex gap-4 text-xs text-muted-foreground">
                      {goal.days_remaining !== null && (
                        <span className="flex items-center gap-1">
                          <Calendar className="h-3 w-3" />
                          {goal.days_remaining}j restants
                        </span>
                      )}
                      {goal.monthly_needed !== null && (
                        <span className="flex items-center gap-1">
                          <TrendingUp className="h-3 w-3" />
                          {formatCurrency(goal.monthly_needed)}/mois
                        </span>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {reachedGoals.length > 0 && (
            <div>
              <h2 className="text-lg font-semibold flex items-center gap-2 mb-3">
                <CheckCircle2 className="h-5 w-5 text-green-500" />
                Objectifs atteints
              </h2>
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {reachedGoals.map((goal) => (
                  <Card key={goal.id} className="opacity-75">
                    <CardContent className="pt-6">
                      <div className="flex items-center gap-3">
                        <div className="h-3 w-3 rounded-full bg-green-500" />
                        <div>
                          <p className="font-medium">{goal.name}</p>
                          <p className="text-sm text-green-500">{formatCurrency(goal.target_amount)} atteint</p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
