import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'
import { calendarApi, predictionsApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import {
  Plus,
  Loader2,
  Trash2,
  Edit,
  Calendar as CalendarIcon,
  Check,
  Clock,
  RefreshCw,
  TrendingUp,
  Building,
  Percent,
  AlertCircle,
  Bell,
  Globe,
  Landmark,
} from 'lucide-react'

interface CalendarEvent {
  id: string
  title: string
  description: string | null
  event_type: string
  event_date: string
  is_recurring: boolean
  recurrence_rule: string | null
  amount: number | null
  currency: string
  is_completed: boolean
  completed_at: string | null
  created_at: string
  source_project_id: string | null
}

interface EventType {
  value: string
  label: string
  color: string
}

interface MarketEvent {
  title: string
  date: string
  category: string
  description: string
  impact: string
  days_until: number
}

interface CalendarSummary {
  total_events: number
  upcoming_events: number
  completed_events: number
  total_expected_income: number
  events_this_month: number
  projected_income_this_month: number
}

const eventTypeIcons: Record<string, React.ReactNode> = {
  dividend: <TrendingUp className="h-4 w-4" />,
  rent: <Building className="h-4 w-4" />,
  interest: <Percent className="h-4 w-4" />,
  payment_due: <AlertCircle className="h-4 w-4" />,
  rebalance: <RefreshCw className="h-4 w-4" />,
  tax_deadline: <CalendarIcon className="h-4 w-4" />,
  reminder: <Bell className="h-4 w-4" />,
  other: <CalendarIcon className="h-4 w-4" />,
}

export default function CalendarPage() {
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const [showAddEvent, setShowAddEvent] = useState(false)
  const [editingEvent, setEditingEvent] = useState<CalendarEvent | null>(null)
  const [showCompleted, setShowCompleted] = useState(false)
  const [showIncomeOnly, setShowIncomeOnly] = useState(false)

  // Fetch event types
  const { data: eventTypes } = useQuery<EventType[]>({
    queryKey: queryKeys.calendar.eventTypes,
    queryFn: calendarApi.getEventTypes,
    staleTime: 10 * 60_000,
  })

  // Fetch events
  const { data: events, isLoading } = useQuery<CalendarEvent[]>({
    queryKey: queryKeys.calendar.events(showCompleted, showIncomeOnly),
    queryFn: () => calendarApi.list({ show_completed: showCompleted, income_only: showIncomeOnly || undefined }),
  })

  // Fetch upcoming events
  const { data: upcomingEvents } = useQuery<CalendarEvent[]>({
    queryKey: queryKeys.calendar.upcoming(),
    queryFn: () => calendarApi.getUpcoming(30),
  })

  // Fetch summary
  const { data: summary } = useQuery<CalendarSummary>({
    queryKey: queryKeys.calendar.summary,
    queryFn: calendarApi.getSummary,
  })

  // Fetch market events
  const { data: marketEvents } = useQuery<MarketEvent[]>({
    queryKey: queryKeys.calendar.marketEvents,
    queryFn: predictionsApi.getMarketEvents,
    staleTime: 5 * 60_000,
  })

  // Create event mutation
  const createMutation = useMutation({
    mutationFn: calendarApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.calendar.all })
      setShowAddEvent(false)
      toast({ title: 'Événement créé', description: 'L\'événement a été ajouté.' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de créer l\'événement.' })
    },
  })

  // Update event mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof calendarApi.update>[1] }) =>
      calendarApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.calendar.all })
      setEditingEvent(null)
      toast({ title: 'Événement mis à jour' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de modifier l\'événement.' })
    },
  })

  // Complete event mutation
  const completeMutation = useMutation({
    mutationFn: calendarApi.complete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.calendar.all })
      toast({ title: 'Événement complété' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de compléter l\'événement.' })
    },
  })

  // Delete event mutation
  const deleteMutation = useMutation({
    mutationFn: calendarApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.calendar.all })
      toast({ title: 'Événement supprimé' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de supprimer l\'événement.' })
    },
  })

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const formData = new FormData(e.currentTarget)

    const data = {
      title: formData.get('title') as string,
      description: formData.get('description') as string || undefined,
      event_type: formData.get('event_type') as string,
      event_date: formData.get('event_date') as string,
      is_recurring: formData.get('is_recurring') === 'on',
      recurrence_rule: formData.get('recurrence_rule') as string || undefined,
      amount: formData.get('amount') ? parseFloat(formData.get('amount') as string) : undefined,
      currency: formData.get('currency') as string || 'EUR',
    }

    if (editingEvent) {
      updateMutation.mutate({ id: editingEvent.id, data })
    } else {
      createMutation.mutate(data)
    }
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('fr-FR', {
      weekday: 'short',
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    })
  }

  const getEventTypeInfo = (type: string) => {
    return eventTypes?.find(t => t.value === type)
  }

  const getEventColor = (event: CalendarEvent) => {
    if (event.source_project_id) return '#10b981' // emerald for crowdfunding
    return getEventTypeInfo(event.event_type)?.color || '#71717a'
  }

  const isOverdue = (event: CalendarEvent) => {
    return !event.is_completed && new Date(event.event_date) < new Date()
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Calendrier</h1>
          <p className="text-muted-foreground">
            Gérez vos échéances et événements financiers.
          </p>
        </div>
        <Button onClick={() => setShowAddEvent(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Nouvel événement
        </Button>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid gap-4 md:grid-cols-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Événements à venir
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{summary.upcoming_events}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Ce mois-ci
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{summary.events_this_month}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Revenus attendus
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-green-600">
                {summary.total_expected_income.toLocaleString('fr-FR')} EUR
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Complétés
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{summary.completed_events}</div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Revenue Banner */}
      {summary && summary.projected_income_this_month > 0 && (
        <Card className="border-emerald-500/30 bg-emerald-500/5">
          <CardContent className="py-3 flex items-center justify-between">
            <span className="text-sm font-medium text-emerald-400 flex items-center gap-2">
              <Landmark className="h-4 w-4" />
              Total revenus projetés ce mois
            </span>
            <span className="text-lg font-bold text-emerald-400">
              +{summary.projected_income_this_month.toLocaleString('fr-FR')} EUR
            </span>
          </CardContent>
        </Card>
      )}

      {/* Market Events Timeline */}
      {marketEvents && marketEvents.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Globe className="h-5 w-5 text-blue-500" />
              Événements marché à venir
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="relative">
              <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-muted" />
              <div className="space-y-4">
                {marketEvents.slice(0, 8).map((event, i) => {
                  const dotColor = event.category === 'crypto' ? 'bg-blue-500' : event.category === 'macro' ? 'bg-purple-500' : 'bg-orange-500'
                  const textColor = event.category === 'crypto' ? 'text-blue-500' : event.category === 'macro' ? 'text-purple-500' : 'text-orange-500'
                  return (
                    <div key={i} className="relative flex items-start gap-4 pl-10">
                      <div className={`absolute left-2.5 top-1.5 w-3 h-3 rounded-full ${dotColor} ring-2 ring-background`} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-medium text-sm">{event.title}</span>
                          <Badge variant="outline" className={`text-xs ${textColor}`}>
                            {event.category}
                          </Badge>
                          {event.impact === 'high' && (
                            <Badge variant="destructive" className="text-xs">Impact fort</Badge>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5">{event.description}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {new Date(event.date).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' })}
                          {' '}· dans {event.days_until} jour{event.days_until > 1 ? 's' : ''}
                        </p>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
            <div className="flex items-center gap-4 mt-4 pt-4 border-t text-xs text-muted-foreground">
              <div className="flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-blue-500" /> Crypto</div>
              <div className="flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-purple-500" /> Macro</div>
              <div className="flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-orange-500" /> Fiscal</div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Upcoming Events */}
      {upcomingEvents && upcomingEvents.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Clock className="h-5 w-5" />
              Prochains événements (30 jours)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {upcomingEvents.slice(0, 5).map((event) => {
                const typeInfo = getEventTypeInfo(event.event_type)
                return (
                  <div
                    key={event.id}
                    className="flex items-center justify-between p-3 rounded-lg border"
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className="h-10 w-10 rounded-full flex items-center justify-center"
                        style={{ backgroundColor: `${typeInfo?.color}20` }}
                      >
                        <span style={{ color: typeInfo?.color }}>
                          {eventTypeIcons[event.event_type]}
                        </span>
                      </div>
                      <div>
                        <p className="font-medium">{event.title}</p>
                        <p className="text-sm text-muted-foreground">
                          {formatDate(event.event_date)}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      {event.amount && (
                        <span className="font-medium text-green-600">
                          +{event.amount.toLocaleString('fr-FR')} {event.currency}
                        </span>
                      )}
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => completeMutation.mutate(event.id)}
                      >
                        <Check className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Filter */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <Checkbox
            id="show-completed"
            checked={showCompleted}
            onCheckedChange={(checked) => setShowCompleted(checked === true)}
          />
          <Label htmlFor="show-completed">Afficher les complétés</Label>
        </div>
        <div className="flex items-center gap-2">
          <Checkbox
            id="income-only"
            checked={showIncomeOnly}
            onCheckedChange={(checked) => setShowIncomeOnly(checked === true)}
          />
          <Label htmlFor="income-only">Revenus uniquement</Label>
        </div>
      </div>

      {/* All Events */}
      {events && events.length > 0 ? (
        <div className="space-y-3">
          {events.map((event) => {
            const color = getEventColor(event)
            const overdue = isOverdue(event)
            const typeInfo = getEventTypeInfo(event.event_type)

            return (
              <Card
                key={event.id}
                className={`${event.is_completed ? 'opacity-60' : ''} ${overdue ? 'border-red-500' : ''}`}
              >
                <CardContent className="py-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div
                        className="h-12 w-12 rounded-full flex items-center justify-center"
                        style={{ backgroundColor: `${color}20` }}
                      >
                        <span style={{ color }}>
                          {event.source_project_id
                            ? <Landmark className="h-4 w-4" />
                            : eventTypeIcons[event.event_type]}
                        </span>
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className={`font-medium ${event.is_completed ? 'line-through' : ''}`}>
                            {event.title}
                          </h3>
                          {event.source_project_id && (
                            <Badge variant="outline" className="text-xs text-emerald-500 border-emerald-500/30">
                              Crowdfunding
                            </Badge>
                          )}
                          {event.is_recurring && (
                            <Badge variant="outline" className="text-xs">
                              <RefreshCw className="h-3 w-3 mr-1" />
                              Récurrent
                            </Badge>
                          )}
                          {overdue && (
                            <Badge variant="destructive" className="text-xs">
                              En retard
                            </Badge>
                          )}
                        </div>
                        <p className="text-sm text-muted-foreground">
                          {formatDate(event.event_date)}
                          {event.description && ` - ${event.description}`}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      {event.amount && (
                        <div className="text-right">
                          <p className="font-medium text-green-600">
                            +{event.amount.toLocaleString('fr-FR')} {event.currency}
                          </p>
                          <Badge style={{ backgroundColor: typeInfo?.color }} className="text-white text-xs">
                            {typeInfo?.label}
                          </Badge>
                        </div>
                      )}
                      <div className="flex gap-1">
                        {!event.is_completed && (
                          <Button
                            size="icon"
                            variant="outline"
                            onClick={() => completeMutation.mutate(event.id)}
                            title="Marquer comme complété"
                          >
                            <Check className="h-4 w-4" />
                          </Button>
                        )}
                        <Button
                          size="icon"
                          variant="ghost"
                          onClick={() => setEditingEvent(event)}
                        >
                          <Edit className="h-4 w-4" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          onClick={() => {
                            if (confirm('Supprimer cet événement ?')) {
                              deleteMutation.mutate(event.id)
                            }
                          }}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    </div>
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
              <CalendarIcon className="h-16 w-16 mx-auto text-muted-foreground" />
              <h2 className="text-xl font-semibold">Aucun événement</h2>
              <p className="text-muted-foreground max-w-md mx-auto">
                Ajoutez des événements pour suivre vos dividendes, loyers et échéances.
              </p>
              <Button onClick={() => setShowAddEvent(true)}>
                <Plus className="h-4 w-4 mr-2" />
                Créer un événement
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Add/Edit Event Dialog */}
      <Dialog
        open={showAddEvent || !!editingEvent}
        onOpenChange={(open) => {
          if (!open) {
            setShowAddEvent(false)
            setEditingEvent(null)
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editingEvent ? 'Modifier l\'événement' : 'Nouvel événement'}
            </DialogTitle>
            <DialogDescription>
              {editingEvent
                ? 'Modifiez les informations de l\'événement.'
                : 'Ajoutez un nouvel événement à votre calendrier.'}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSubmit}>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="title">Titre *</Label>
                <Input
                  id="title"
                  name="title"
                  defaultValue={editingEvent?.title || ''}
                  placeholder="Dividende Apple"
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="event_type">Type *</Label>
                <Select
                  name="event_type"
                  defaultValue={editingEvent?.event_type || 'dividend'}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Sélectionnez un type" />
                  </SelectTrigger>
                  <SelectContent>
                    {eventTypes?.map((type) => (
                      <SelectItem key={type.value} value={type.value}>
                        <div className="flex items-center gap-2">
                          <div
                            className="h-3 w-3 rounded-full"
                            style={{ backgroundColor: type.color }}
                          />
                          {type.label}
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="event_date">Date *</Label>
                <Input
                  id="event_date"
                  name="event_date"
                  type="datetime-local"
                  defaultValue={
                    editingEvent
                      ? new Date(editingEvent.event_date).toISOString().slice(0, 16)
                      : ''
                  }
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="amount">Montant</Label>
                  <Input
                    id="amount"
                    name="amount"
                    type="number"
                    step="0.01"
                    defaultValue={editingEvent?.amount || ''}
                    placeholder="100.00"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="currency">Devise</Label>
                  <Select name="currency" defaultValue={editingEvent?.currency || 'EUR'}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="EUR">EUR</SelectItem>
                      <SelectItem value="USD">USD</SelectItem>
                      <SelectItem value="GBP">GBP</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="description">Description</Label>
                <Textarea
                  id="description"
                  name="description"
                  defaultValue={editingEvent?.description || ''}
                  placeholder="Détails de l'événement..."
                  rows={2}
                />
              </div>

              <div className="flex items-center gap-2">
                <Checkbox
                  id="is_recurring"
                  name="is_recurring"
                  defaultChecked={editingEvent?.is_recurring || false}
                />
                <Label htmlFor="is_recurring">Événement récurrent</Label>
              </div>

              <div className="space-y-2">
                <Label htmlFor="recurrence_rule">Fréquence de récurrence</Label>
                <Select
                  name="recurrence_rule"
                  defaultValue={editingEvent?.recurrence_rule || ''}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Sélectionnez une fréquence" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="DAILY">Quotidien</SelectItem>
                    <SelectItem value="WEEKLY">Hebdomadaire</SelectItem>
                    <SelectItem value="MONTHLY">Mensuel</SelectItem>
                    <SelectItem value="YEARLY">Annuel</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setShowAddEvent(false)
                  setEditingEvent(null)
                }}
              >
                Annuler
              </Button>
              <Button
                type="submit"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                {(createMutation.isPending || updateMutation.isPending) && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                {editingEvent ? 'Enregistrer' : 'Créer'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
