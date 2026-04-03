import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { queryKeys } from '@/lib/queryKeys'
import { strategiesApi } from '@/services/api'
import { toast } from '@/hooks/use-toast'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  Brain,
  Plus,
  Check,
  X,
  Loader2,
  Sparkles,
  TrendingUp,
  TrendingDown,
  Shield,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  CircleDot,
  Trash2,
  Wallet,
} from 'lucide-react'

// Types
interface StrategyAction {
  id: string
  strategy_id: string
  action: string
  symbol: string | null
  amount: number | null
  currency: string
  reason: string | null
  status: string
  scheduled_at: string | null
  executed_at: string | null
  created_at: string
}

interface Strategy {
  id: string
  user_id: string
  name: string
  description: string | null
  source: 'AI' | 'USER'
  status: string
  params: Record<string, unknown>
  ai_reasoning: string | null
  market_regime: string | null
  confidence: number | null
  actions: StrategyAction[]
  created_at: string
  updated_at: string
}

const STATUS_BADGE: Record<string, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  PROPOSED: { label: 'Proposée', variant: 'secondary' },
  ACTIVE: { label: 'Active', variant: 'default' },
  PAUSED: { label: 'En pause', variant: 'outline' },
  COMPLETED: { label: 'Terminée', variant: 'secondary' },
  REJECTED: { label: 'Rejetée', variant: 'destructive' },
}

const ACTION_BADGE: Record<string, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  PENDING: { label: 'En attente', variant: 'outline' },
  EXECUTED: { label: 'Exécutée', variant: 'default' },
  SKIPPED: { label: 'Ignorée', variant: 'secondary' },
}

function getStrategyIcon(params: Record<string, unknown>) {
  const type = (params?.type as string) || ''
  if (type.includes('defensive') || type.includes('observation')) return Shield
  if (type.includes('profit')) return TrendingDown
  if (type.includes('rebalance')) return RefreshCw
  return TrendingUp
}

const RISK_LABELS: Record<number, { label: string; color: string }> = {
  1: { label: 'Conservateur', color: 'text-emerald-400 border-emerald-400/30' },
  2: { label: 'Modéré', color: 'text-blue-400 border-blue-400/30' },
  3: { label: 'Dynamique', color: 'text-amber-400 border-amber-400/30' },
  4: { label: 'Agressif', color: 'text-red-400 border-red-400/30' },
}

const PERF_LABELS: Record<number, string> = {
  1: 'Faible',
  2: 'Moyen',
  3: 'Élevé',
  4: 'Très élevé',
}

function StrategyCard({
  strategy,
  onAccept,
  onReject,
  onDelete,
  onMarkAction,
  onUpdateAmount,
}: {
  strategy: Strategy
  onAccept: (id: string) => void
  onReject: (id: string) => void
  onDelete: (id: string) => void
  onMarkAction: (actionId: string, status: string) => void
  onUpdateAmount: (actionId: string, amount: number) => void
}) {
  const [expanded, setExpanded] = useState(strategy.status === 'PROPOSED')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editAmount, setEditAmount] = useState('')
  const Icon = getStrategyIcon(strategy.params)
  const statusBadge = STATUS_BADGE[strategy.status] || STATUS_BADGE.ACTIVE
  const pendingActions = strategy.actions.filter((a) => a.status === 'PENDING')
  const riskLevel = (strategy.params?.risk_level as number) || 0
  const perfLevel = (strategy.params?.performance_potential as number) || 0
  const riskInfo = RISK_LABELS[riskLevel]
  const perfLabel = PERF_LABELS[perfLevel]

  return (
    <Card className={strategy.status === 'PROPOSED' ? 'border-indigo-500/30 bg-indigo-500/5' : ''}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 flex-1 min-w-0">
            <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0 mt-0.5">
              <Icon className="h-5 w-5 text-primary" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <CardTitle className="text-base">{strategy.name}</CardTitle>
                <Badge variant={statusBadge.variant}>{statusBadge.label}</Badge>
                {strategy.source === 'AI' && (
                  <Badge variant="outline" className="text-indigo-400 border-indigo-400/30">
                    <Sparkles className="h-3 w-3 mr-1" />
                    IA
                  </Badge>
                )}
                {strategy.market_regime && (
                  <Badge variant="outline" className="text-xs">
                    {strategy.market_regime}
                    {strategy.confidence ? ` · ${(strategy.confidence * 100).toFixed(0)}%` : ''}
                  </Badge>
                )}
                {riskInfo && (
                  <Badge variant="outline" className={`text-xs ${riskInfo.color}`}>
                    {riskInfo.label}
                  </Badge>
                )}
                {perfLabel && (
                  <Badge variant="outline" className="text-xs">
                    Perf. {perfLabel}
                  </Badge>
                )}
              </div>
              {strategy.description && (
                <p className="text-sm text-muted-foreground mt-1">{strategy.description}</p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {strategy.status === 'PROPOSED' && (
              <>
                <Button size="sm" variant="default" onClick={() => onAccept(strategy.id)}>
                  <Check className="h-4 w-4 mr-1" />
                  Accepter
                </Button>
                <Button size="sm" variant="outline" onClick={() => onReject(strategy.id)}>
                  <X className="h-4 w-4" />
                </Button>
              </>
            )}
            {strategy.source === 'USER' && (
              <Button size="sm" variant="ghost" onClick={() => onDelete(strategy.id)}>
                <Trash2 className="h-4 w-4 text-muted-foreground" />
              </Button>
            )}
            <Button size="sm" variant="ghost" onClick={() => setExpanded(!expanded)}>
              {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </CardHeader>

      {expanded && strategy.actions.length > 0 && (
        <CardContent className="pt-0">
          {strategy.source === 'AI' && (strategy.params?.available_liquidity as number) > 0 && (
            <div className="mb-3 flex items-center gap-4 p-2.5 rounded-md bg-emerald-500/5 border border-emerald-500/10 text-sm">
              <div className="flex items-center gap-1.5 text-emerald-400">
                <Wallet className="h-3.5 w-3.5" />
                <span className="font-medium">
                  Munitions : {(strategy.params.available_liquidity as number).toLocaleString('fr-FR', { maximumFractionDigits: 0 })} €
                </span>
              </div>
              {(strategy.params?.total_proposed_amount as number) > 0 && (
                <span className="text-muted-foreground">
                  Montant proposé : {(strategy.params.total_proposed_amount as number).toLocaleString('fr-FR', { maximumFractionDigits: 0 })} €
                  {' '}({(strategy.params.proposed_pct_of_liquidity as number)?.toFixed(1)}% des liquidités)
                </span>
              )}
            </div>
          )}
          {strategy.ai_reasoning && strategy.source === 'AI' && (
            <div className="mb-4 p-3 rounded-md bg-indigo-500/5 border border-indigo-500/10">
              <p className="text-sm text-muted-foreground italic">{strategy.ai_reasoning}</p>
            </div>
          )}
          <div className="space-y-2">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Actions ({pendingActions.length} en attente)
            </p>
            {strategy.actions.map((action) => {
              const actionBadge = ACTION_BADGE[action.status] || ACTION_BADGE.PENDING
              const isEditing = editingId === action.id
              return (
                <div
                  key={action.id}
                  className="flex items-center justify-between p-3 rounded-md bg-muted/30 gap-3"
                >
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    <CircleDot className="h-4 w-4 text-muted-foreground shrink-0" />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-medium">{action.action}</span>
                        {action.symbol && (
                          <Badge variant="outline" className="text-xs">{action.symbol}</Badge>
                        )}
                        {action.amount != null && action.amount > 0 && (
                          isEditing ? (
                            <div className="flex items-center gap-1">
                              <Input
                                type="number"
                                step="0.01"
                                min="0"
                                className="h-7 w-24 text-sm"
                                value={editAmount}
                                onChange={(e) => setEditAmount(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') {
                                    const val = parseFloat(editAmount)
                                    if (val > 0) onUpdateAmount(action.id, val)
                                    setEditingId(null)
                                  }
                                  if (e.key === 'Escape') setEditingId(null)
                                }}
                                autoFocus
                              />
                              <span className="text-xs text-muted-foreground">{action.currency}</span>
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-6 w-6 p-0"
                                onClick={() => {
                                  const val = parseFloat(editAmount)
                                  if (val > 0) onUpdateAmount(action.id, val)
                                  setEditingId(null)
                                }}
                              >
                                <Check className="h-3 w-3" />
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-6 w-6 p-0"
                                onClick={() => setEditingId(null)}
                              >
                                <X className="h-3 w-3" />
                              </Button>
                            </div>
                          ) : (
                            <button
                              type="button"
                              className={`text-sm ${action.status === 'PENDING' ? 'text-foreground underline decoration-dashed underline-offset-4 cursor-pointer hover:text-primary' : 'text-muted-foreground'}`}
                              disabled={action.status !== 'PENDING'}
                              onClick={() => {
                                if (action.status === 'PENDING') {
                                  setEditingId(action.id)
                                  setEditAmount(String(action.amount))
                                }
                              }}
                              title={action.status === 'PENDING' ? 'Cliquer pour modifier le montant' : undefined}
                            >
                              {action.amount.toLocaleString('fr-FR', { maximumFractionDigits: 2 })} {action.currency}
                            </button>
                          )
                        )}
                        <Badge variant={actionBadge.variant} className="text-xs">{actionBadge.label}</Badge>
                      </div>
                      {action.reason && (
                        <p className="text-xs text-muted-foreground mt-0.5">{action.reason}</p>
                      )}
                    </div>
                  </div>
                  {action.status === 'PENDING' && (
                    <div className="flex gap-1 shrink-0">
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7 text-xs"
                        onClick={() => onMarkAction(action.id, 'EXECUTED')}
                      >
                        <Check className="h-3 w-3 mr-1" />
                        Fait
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 text-xs"
                        onClick={() => onMarkAction(action.id, 'SKIPPED')}
                      >
                        Ignorer
                      </Button>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </CardContent>
      )}
    </Card>
  )
}

interface FormAction {
  action: string
  symbol: string
  amount: string
  currency: string
  reason: string
}

const EMPTY_ACTION: FormAction = { action: 'DCA', symbol: '', amount: '', currency: 'EUR', reason: '' }

const ACTION_TYPES = [
  'DCA',
  'ACHAT',
  'VENDRE',
  'ALLÉGER',
  'RENFORCER',
  'PRENDRE PROFITS',
  'HOLD',
  'SWAP',
] as const

export default function StrategiesPage() {
  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [formName, setFormName] = useState('')
  const [formDesc, setFormDesc] = useState('')
  const [formActions, setFormActions] = useState<FormAction[]>([{ ...EMPTY_ACTION }])

  const resetForm = () => {
    setFormName('')
    setFormDesc('')
    setFormActions([{ ...EMPTY_ACTION }])
  }

  const updateAction = (idx: number, field: keyof FormAction, value: string) => {
    setFormActions((prev) => prev.map((a, i) => (i === idx ? { ...a, [field]: value } : a)))
  }

  const removeAction = (idx: number) => {
    setFormActions((prev) => prev.filter((_, i) => i !== idx))
  }

  const addAction = () => {
    setFormActions((prev) => [...prev, { ...EMPTY_ACTION }])
  }

  // Fetch strategies
  const { data: strategies = [], isLoading } = useQuery<Strategy[]>({
    queryKey: queryKeys.strategies.list,
    queryFn: strategiesApi.list,
  })

  // AI suggest
  const suggestMutation = useMutation({
    mutationFn: strategiesApi.aiSuggest,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.strategies.all })
      toast({ title: 'Analyse terminée', description: 'Nouvelles stratégies proposées par l\'IA.' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de générer des suggestions.' })
    },
  })

  // Create user strategy
  const createMutation = useMutation({
    mutationFn: strategiesApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.strategies.all })
      setCreateOpen(false)
      resetForm()
      toast({ title: 'Stratégie créée' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de créer la stratégie.' })
    },
  })

  // Accept / Reject
  const acceptMutation = useMutation({
    mutationFn: strategiesApi.accept,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.strategies.all }),
  })

  const rejectMutation = useMutation({
    mutationFn: strategiesApi.reject,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.strategies.all }),
  })

  const deleteMutation = useMutation({
    mutationFn: strategiesApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.strategies.all })
      toast({ title: 'Stratégie supprimée' })
    },
  })

  // Mark action
  const markActionMutation = useMutation({
    mutationFn: ({ actionId, status }: { actionId: string; status: string }) =>
      strategiesApi.updateAction(actionId, { status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.strategies.all }),
  })

  // Update action amount
  const updateAmountMutation = useMutation({
    mutationFn: ({ actionId, amount }: { actionId: string; amount: number }) =>
      strategiesApi.updateAction(actionId, { amount }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.strategies.all })
      toast({ title: 'Montant mis à jour' })
    },
  })

  // Group strategies
  const proposed = useMemo(() => strategies.filter((s) => s.status === 'PROPOSED'), [strategies])
  const active = useMemo(() => strategies.filter((s) => s.status === 'ACTIVE'), [strategies])
  const archived = useMemo(
    () => strategies.filter((s) => ['COMPLETED', 'REJECTED', 'PAUSED'].includes(s.status)),
    [strategies],
  )

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Stratégies</h1>
          <p className="text-muted-foreground">
            Laissez l'IA analyser votre portefeuille ou créez vos propres stratégies.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Nouvelle stratégie
          </Button>
          <Button onClick={() => suggestMutation.mutate()} disabled={suggestMutation.isPending}>
            {suggestMutation.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Brain className="h-4 w-4 mr-2" />
            )}
            Analyser mon portefeuille
          </Button>
        </div>
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center h-40">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* AI Proposals */}
      {proposed.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-indigo-400" />
            Propositions IA
            <Badge variant="secondary">{proposed.length}</Badge>
          </h2>
          {proposed.map((s) => (
            <StrategyCard
              key={s.id}
              strategy={s}
              onAccept={(id) => acceptMutation.mutate(id)}
              onReject={(id) => rejectMutation.mutate(id)}
              onDelete={(id) => deleteMutation.mutate(id)}
              onMarkAction={(actionId, status) => markActionMutation.mutate({ actionId, status })}
              onUpdateAmount={(actionId, amount) => updateAmountMutation.mutate({ actionId, amount })}
            />
          ))}
        </div>
      )}

      {/* Active strategies */}
      {active.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold">Stratégies actives</h2>
          {active.map((s) => (
            <StrategyCard
              key={s.id}
              strategy={s}
              onAccept={(id) => acceptMutation.mutate(id)}
              onReject={(id) => rejectMutation.mutate(id)}
              onDelete={(id) => deleteMutation.mutate(id)}
              onMarkAction={(actionId, status) => markActionMutation.mutate({ actionId, status })}
              onUpdateAmount={(actionId, amount) => updateAmountMutation.mutate({ actionId, amount })}
            />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isLoading && strategies.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <Brain className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold mb-2">Aucune stratégie</h3>
            <p className="text-muted-foreground mb-4 max-w-md">
              Cliquez sur "Analyser mon portefeuille" pour que l'IA propose des stratégies
              adaptées à votre situation, ou créez les vôtres.
            </p>
            <Button onClick={() => suggestMutation.mutate()} disabled={suggestMutation.isPending}>
              {suggestMutation.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Brain className="h-4 w-4 mr-2" />
              )}
              Analyser mon portefeuille
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Archived */}
      {archived.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold text-muted-foreground">Historique</h2>
          {archived.map((s) => (
            <StrategyCard
              key={s.id}
              strategy={s}
              onAccept={(id) => acceptMutation.mutate(id)}
              onReject={(id) => rejectMutation.mutate(id)}
              onDelete={(id) => deleteMutation.mutate(id)}
              onMarkAction={(actionId, status) => markActionMutation.mutate({ actionId, status })}
              onUpdateAmount={(actionId, amount) => updateAmountMutation.mutate({ actionId, amount })}
            />
          ))}
        </div>
      )}

      {/* Create dialog */}
      <Dialog open={createOpen} onOpenChange={(open) => { setCreateOpen(open); if (!open) resetForm() }}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Nouvelle stratégie</DialogTitle>
          </DialogHeader>
          <div className="space-y-5 py-4">
            {/* Name */}
            <div className="space-y-2">
              <Label htmlFor="strategy-name">Nom de la stratégie</Label>
              <Input
                id="strategy-name"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                placeholder="Ex: DCA Bitcoin hebdomadaire"
              />
            </div>

            {/* Description */}
            <div className="space-y-2">
              <Label htmlFor="strategy-desc">Description / Règles</Label>
              <Textarea
                id="strategy-desc"
                value={formDesc}
                onChange={(e) => setFormDesc(e.target.value)}
                placeholder="Décrivez votre stratégie, vos règles d'entrée/sortie, conditions de marché..."
                rows={3}
              />
            </div>

            {/* Actions */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label>Actions prévues</Label>
                <Button type="button" variant="outline" size="sm" onClick={addAction}>
                  <Plus className="h-3 w-3 mr-1" />
                  Ajouter
                </Button>
              </div>

              {formActions.map((fa, idx) => (
                <div key={idx} className="p-3 rounded-lg border border-white/[0.08] bg-muted/20 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-muted-foreground">Action {idx + 1}</span>
                    {formActions.length > 1 && (
                      <Button type="button" variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => removeAction(idx)}>
                        <X className="h-3 w-3" />
                      </Button>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <Label className="text-xs">Type</Label>
                      <Select value={fa.action} onValueChange={(v) => updateAction(idx, 'action', v)}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {ACTION_TYPES.map((t) => (
                            <SelectItem key={t} value={t}>{t}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">Symbole</Label>
                      <Input
                        value={fa.symbol}
                        onChange={(e) => updateAction(idx, 'symbol', e.target.value.toUpperCase())}
                        placeholder="BTC, ETH, SOL..."
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">Montant</Label>
                      <Input
                        type="number"
                        step="0.01"
                        min="0"
                        value={fa.amount}
                        onChange={(e) => updateAction(idx, 'amount', e.target.value)}
                        placeholder="100"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">Devise</Label>
                      <Select value={fa.currency} onValueChange={(v) => updateAction(idx, 'currency', v)}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="EUR">EUR</SelectItem>
                          <SelectItem value="USD">USD</SelectItem>
                          <SelectItem value="BTC">BTC</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Raison / Note</Label>
                    <Input
                      value={fa.reason}
                      onChange={(e) => updateAction(idx, 'reason', e.target.value)}
                      placeholder="Ex: Accumuler pendant le bear market"
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setCreateOpen(false); resetForm() }}>
              Annuler
            </Button>
            <Button
              onClick={() => {
                const actions = formActions
                  .filter((a) => a.symbol.trim() || a.action === 'HOLD')
                  .map((a) => ({
                    action: a.action,
                    symbol: a.symbol.trim() || undefined,
                    amount: a.amount ? parseFloat(a.amount) : undefined,
                    currency: a.currency,
                    reason: a.reason.trim() || undefined,
                  }))
                createMutation.mutate({ name: formName, description: formDesc, actions })
              }}
              disabled={!formName.trim() || createMutation.isPending}
            >
              {createMutation.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Créer la stratégie
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
