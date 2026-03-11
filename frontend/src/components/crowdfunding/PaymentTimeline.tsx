import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useToast } from '@/hooks/use-toast'
import { crowdfundingApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import { formatCurrency } from '@/lib/utils'
import {
  CheckCircle2,
  Circle,
  AlertTriangle,
  Loader2,
  Banknote,
  ChevronDown,
  Clock,
  TrendingUp,
  CalendarCheck,
  Timer,
} from 'lucide-react'
import type {
  PaymentScheduleEntry,
  ScheduleStatus,
  CrowdfundingProject,
} from '@/types/crowdfunding'
import { useState, useMemo } from 'react'

const STATUS_CONFIG: Record<
  ScheduleStatus,
  { icon: typeof CheckCircle2; color: string; label: string; bg: string; dot: string }
> = {
  paid: {
    icon: CheckCircle2,
    color: 'text-emerald-400',
    label: 'Payé',
    bg: 'bg-emerald-500/10 ring-1 ring-emerald-500/20',
    dot: 'bg-emerald-500',
  },
  pending: {
    icon: Circle,
    color: 'text-amber-400',
    label: 'En attente',
    bg: 'bg-amber-500/10 ring-1 ring-amber-500/20',
    dot: 'bg-amber-500',
  },
  overdue: {
    icon: AlertTriangle,
    color: 'text-red-400',
    label: 'En retard',
    bg: 'bg-red-500/10 ring-1 ring-red-500/20',
    dot: 'bg-red-500',
  },
}

const today = () => new Date().toISOString().split('T')[0]

interface PaymentTimelineProps {
  project: CrowdfundingProject
}

export default function PaymentTimeline({ project }: PaymentTimelineProps) {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [optimisticPaid, setOptimisticPaid] = useState<Set<string>>(new Set())
  const [showPaid, setShowPaid] = useState(false)

  const schedule = project.schedule ?? []

  const markPaidMutation = useMutation({
    mutationFn: async ({ entry, paymentDate, amount }: { entry: PaymentScheduleEntry; paymentDate: string; amount: number }) => {
      return crowdfundingApi.createRepayment(project.id, {
        payment_date: paymentDate,
        amount,
        payment_type:
          entry.expected_capital > 0 && entry.expected_interest > 0
            ? 'both'
            : entry.expected_capital > 0
              ? 'capital'
              : 'interest',
        interest_amount: entry.expected_interest > 0 ? entry.expected_interest : undefined,
        capital_amount: entry.expected_capital > 0 ? entry.expected_capital : undefined,
      })
    },
    onMutate: ({ entry }) => {
      setOptimisticPaid((prev) => new Set(prev).add(entry.id))
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.crowdfunding.all })
      toast({ title: 'Remboursement enregistré' })
    },
    onError: (_err, { entry }) => {
      setOptimisticPaid((prev) => {
        const next = new Set(prev)
        next.delete(entry.id)
        return next
      })
      toast({
        title: "Erreur lors de l'enregistrement",
        variant: 'destructive',
      })
    },
    onSettled: (_data, _err, { entry }) => {
      setOptimisticPaid((prev) => {
        const next = new Set(prev)
        next.delete(entry.id)
        return next
      })
    },
  })

  // Index repayments by id for quick lookup (normalize UUID casing)
  const repaymentMap = useMemo(() => {
    const map = new Map<string, { amount: number; payment_date: string; interest_amount: number | null; capital_amount: number | null }>()
    for (const r of project.repayments ?? []) {
      map.set(String(r.id).toLowerCase(), r)
    }
    return map
  }, [project.repayments])

  const { paidEntries, activeEntries, stats } = useMemo(() => {
    const paid: (PaymentScheduleEntry & { effectiveStatus: ScheduleStatus; actualAmount?: number; actualDate?: string })[] = []
    const active: (PaymentScheduleEntry & { effectiveStatus: ScheduleStatus })[] = []
    let overdueCount = 0
    let pendingCount = 0
    let totalExpectedCapital = 0
    let paidCapital = 0
    let totalExpectedInterest = 0
    let paidInterest = 0
    let totalActualReceived = 0

    for (const entry of schedule) {
      const isOptimistic = optimisticPaid.has(entry.id)
      const effectiveStatus: ScheduleStatus = isOptimistic ? 'paid' : entry.status

      totalExpectedCapital += Number(entry.expected_capital)
      totalExpectedInterest += Number(entry.expected_interest)

      if (effectiveStatus === 'paid') {
        const repayment = entry.repayment_id ? repaymentMap.get(String(entry.repayment_id).toLowerCase()) : undefined
        const actualAmount = repayment ? Number(repayment.amount) : (Number(entry.expected_capital) + Number(entry.expected_interest))
        const actualDate = repayment?.payment_date
        paid.push({ ...entry, effectiveStatus, actualAmount, actualDate })
        paidCapital += Number(entry.expected_capital)
        paidInterest += Number(entry.expected_interest)
        totalActualReceived += actualAmount
      } else {
        active.push({ ...entry, effectiveStatus })
        if (effectiveStatus === 'overdue') overdueCount++
        else pendingCount++
      }
    }

    const recoveryPercent = totalExpectedCapital > 0
      ? Math.min(100, (paidCapital / totalExpectedCapital) * 100)
      : 0

    return {
      paidEntries: paid,
      activeEntries: active,
      stats: {
        overdueCount,
        pendingCount,
        paidCount: paid.length,
        total: schedule.length,
        recoveryPercent,
        totalExpectedCapital,
        paidCapital,
        totalExpectedInterest,
        paidInterest,
        totalActualReceived,
      },
    }
  }, [schedule, optimisticPaid, repaymentMap])

  if (schedule.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
        <Clock className="h-8 w-8 mb-3 opacity-50" />
        <p className="text-sm">Aucun échéancier disponible</p>
        <p className="text-xs mt-1">Ajoutez une date de début au projet pour générer l'échéancier</p>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      {/* Summary stats row */}
      <div className="grid grid-cols-4 gap-3">
        <div className="rounded-xl bg-emerald-500/5 border border-emerald-500/10 p-3 text-center">
          <p className="text-2xl font-bold tabular-nums text-emerald-400">{stats.paidCount}</p>
          <p className="text-[11px] text-muted-foreground mt-0.5">Payées</p>
        </div>
        <div className="rounded-xl bg-amber-500/5 border border-amber-500/10 p-3 text-center">
          <p className="text-2xl font-bold tabular-nums text-amber-400">{stats.pendingCount}</p>
          <p className="text-[11px] text-muted-foreground mt-0.5">En attente</p>
        </div>
        <div className={`rounded-xl p-3 text-center ${stats.overdueCount > 0 ? 'bg-red-500/5 border border-red-500/10' : 'bg-muted/30 border border-border/50'}`}>
          <p className={`text-2xl font-bold tabular-nums ${stats.overdueCount > 0 ? 'text-red-400' : 'text-muted-foreground'}`}>{stats.overdueCount}</p>
          <p className="text-[11px] text-muted-foreground mt-0.5">En retard</p>
        </div>
        <div className="rounded-xl bg-muted/30 border border-border/50 p-3 text-center">
          <p className="text-2xl font-bold tabular-nums">{stats.recoveryPercent.toFixed(0)}%</p>
          <p className="text-[11px] text-muted-foreground mt-0.5">Capital récupéré</p>
        </div>
      </div>

      {/* Delay banner */}
      {project.delay_months > 0 && (
        <div className="flex items-center gap-2 rounded-lg bg-orange-500/10 border border-orange-500/20 px-3 py-2">
          <Timer className="h-4 w-4 text-orange-400 shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-orange-400">
              Retard constaté : +{project.delay_months} mois
            </p>
            <p className="text-[11px] text-muted-foreground">
              Fin contractuelle : {project.estimated_end_date
                ? new Date(project.estimated_end_date).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' })
                : '—'}
              {' → '}Fin estimée : {project.estimated_end_date
                ? new Date(new Date(project.estimated_end_date).setMonth(new Date(project.estimated_end_date).getMonth() + project.delay_months)).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' })
                : '—'}
            </p>
          </div>
        </div>
      )}

      {/* Capital recovery bar */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground flex items-center gap-1.5">
            <TrendingUp className="h-3 w-3" />
            Récupération du capital
          </span>
          <span className="tabular-nums font-medium">
            {formatCurrency(stats.paidCapital)} / {formatCurrency(stats.totalExpectedCapital)}
          </span>
        </div>
        <div className="h-2 bg-muted/50 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-700 ease-out bg-gradient-to-r from-emerald-500 to-emerald-400"
            style={{ width: `${stats.recoveryPercent}%` }}
          />
        </div>
      </div>

      {/* Paid entries (collapsible) */}
      {paidEntries.length > 0 && (
        <div>
          <button
            onClick={() => setShowPaid(!showPaid)}
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors mb-2"
          >
            <ChevronDown className={`h-3 w-3 transition-transform duration-200 ${showPaid ? 'rotate-180' : ''}`} />
            {paidEntries.length} échéance{paidEntries.length > 1 ? 's' : ''} payée{paidEntries.length > 1 ? 's' : ''}
          </button>
          {showPaid && (
            <div className="space-y-1 pl-1">
              {paidEntries.map((entry) => (
                <TimelineRow
                  key={entry.id}
                  entry={entry}
                  effectiveStatus="paid"
                  isOptimistic={optimisticPaid.has(entry.id)}
                  actualAmount={entry.actualAmount}
                  actualDate={entry.actualDate}
                  compact
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Active entries (pending + overdue) */}
      {activeEntries.length > 0 && (
        <div className="space-y-1">
          {paidEntries.length > 0 && activeEntries.length > 0 && (
            <p className="text-xs text-muted-foreground mb-2 font-medium">Échéances à venir</p>
          )}
          {activeEntries.map((entry) => (
            <TimelineRow
              key={entry.id}
              entry={entry}
              effectiveStatus={entry.effectiveStatus}
              isOptimistic={optimisticPaid.has(entry.id)}
              onMarkPaid={(paymentDate, amount) => markPaidMutation.mutate({ entry, paymentDate, amount })}
              isPendingMutation={markPaidMutation.isPending}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function TimelineRow({
  entry,
  effectiveStatus,
  isOptimistic,
  onMarkPaid,
  isPendingMutation,
  actualAmount,
  actualDate,
  compact,
}: {
  entry: PaymentScheduleEntry
  effectiveStatus: ScheduleStatus
  isOptimistic: boolean
  onMarkPaid?: (paymentDate: string, amount: number) => void
  isPendingMutation?: boolean
  actualAmount?: number
  actualDate?: string
  compact?: boolean
}) {
  const config = STATUS_CONFIG[effectiveStatus]
  const Icon = config.icon
  const expectedAmount = Number(entry.expected_capital) + Number(entry.expected_interest)
  const isPending = effectiveStatus === 'pending' || effectiveStatus === 'overdue'
  const [paymentDate, setPaymentDate] = useState(today)
  const [editedAmount, setEditedAmount] = useState(expectedAmount.toFixed(2))
  const [popoverOpen, setPopoverOpen] = useState(false)
  const displayAmount = effectiveStatus === 'paid' && actualAmount != null ? Number(actualAmount) : expectedAmount
  const displayDate = effectiveStatus === 'paid' && actualDate ? actualDate : entry.due_date

  return (
    <div
      className={`group flex items-center gap-3 rounded-lg px-3 transition-colors duration-150 ${
        compact ? 'py-1.5' : 'py-2.5 hover:bg-muted/30'
      } ${effectiveStatus === 'overdue' ? 'bg-red-500/[0.03]' : ''}`}
    >
      {/* Status icon */}
      <div className={`flex items-center justify-center w-7 h-7 rounded-full shrink-0 ${config.bg} transition-all duration-300 ${
        isOptimistic ? 'scale-110' : ''
      }`}>
        {isOptimistic ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-emerald-400" />
        ) : (
          <Icon className={`h-3.5 w-3.5 ${config.color}`} />
        )}
      </div>

      {/* Date */}
      <div className={`min-w-[90px] ${compact ? 'text-xs' : 'text-sm'}`}>
        <span className={effectiveStatus === 'paid' && !compact ? 'text-muted-foreground' : 'font-medium'}>
          {new Date(displayDate).toLocaleDateString('fr-FR', {
            day: 'numeric',
            month: 'short',
            year: compact ? undefined : 'numeric',
          })}
        </span>
      </div>

      {/* Breakdown */}
      <div className="flex-1 flex items-center gap-3 min-w-0">
        {entry.expected_interest > 0 && (
          <span className={`text-xs tabular-nums ${compact ? 'text-muted-foreground' : ''}`}>
            <span className="text-muted-foreground">Int. </span>
            {formatCurrency(entry.expected_interest)}
          </span>
        )}
        {entry.expected_capital > 0 && (
          <span className={`text-xs tabular-nums ${compact ? 'text-muted-foreground' : ''}`}>
            <span className="text-muted-foreground">Cap. </span>
            {formatCurrency(entry.expected_capital)}
          </span>
        )}
      </div>

      {/* Total amount */}
      <span className={`text-sm font-semibold tabular-nums shrink-0 ${
        effectiveStatus === 'paid'
          ? 'text-emerald-400'
          : effectiveStatus === 'overdue'
            ? 'text-red-400'
            : ''
      }`}>
        {formatCurrency(displayAmount)}
      </span>

      {/* Action */}
      <div className="w-[110px] shrink-0 flex justify-end">
        {isPending && !isOptimistic && onMarkPaid && (
          <Popover open={popoverOpen} onOpenChange={setPopoverOpen}>
            <PopoverTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2.5 text-xs opacity-0 group-hover:opacity-100 transition-opacity hover:bg-emerald-500/10 hover:text-emerald-400"
                disabled={isPendingMutation}
              >
                <Banknote className="h-3.5 w-3.5 mr-1" />
                Reçu
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-56 p-3" align="end" side="top">
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium flex items-center gap-1.5 text-muted-foreground">
                    <CalendarCheck className="h-3 w-3" />
                    Date de réception
                  </label>
                  <Input
                    type="date"
                    value={paymentDate}
                    onChange={(e) => setPaymentDate(e.target.value)}
                    className="h-8 text-xs"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium flex items-center gap-1.5 text-muted-foreground">
                    <Banknote className="h-3 w-3" />
                    Montant reçu (€)
                  </label>
                  <Input
                    type="number"
                    step="0.01"
                    min="0"
                    value={editedAmount}
                    onChange={(e) => setEditedAmount(e.target.value)}
                    className="h-8 text-xs"
                  />
                  {parseFloat(editedAmount) !== expectedAmount && (
                    <p className="text-[10px] text-muted-foreground">
                      Attendu : {formatCurrency(expectedAmount)}
                    </p>
                  )}
                </div>
                <Button
                  size="sm"
                  className="w-full h-7 text-xs bg-emerald-600 hover:bg-emerald-700"
                  onClick={() => {
                    onMarkPaid(paymentDate, parseFloat(editedAmount) || expectedAmount)
                    setPopoverOpen(false)
                  }}
                  disabled={isPendingMutation || !paymentDate || (parseFloat(editedAmount) || 0) <= 0}
                >
                  {isPendingMutation ? (
                    <Loader2 className="h-3 w-3 animate-spin mr-1" />
                  ) : (
                    <CheckCircle2 className="h-3 w-3 mr-1" />
                  )}
                  Confirmer
                </Button>
              </div>
            </PopoverContent>
          </Popover>
        )}
        {effectiveStatus === 'paid' && !isOptimistic && !compact && (
          <Badge variant="outline" className="text-emerald-400 border-emerald-500/20 text-[10px] px-1.5">
            Payé
          </Badge>
        )}
      </div>
    </div>
  )
}
