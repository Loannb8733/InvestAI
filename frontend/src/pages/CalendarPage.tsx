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

  // Fetch event types
  const { data: eventTypes } = useQuery<EventType[]>({
    queryKey: ['event-types'],
    queryFn: calendarApi.getEventTypes,
  })

  // Fetch events
  const { data: events, isLoading } = useQuery<CalendarEvent[]>({
    queryKey: ['calendar-events', showCompleted],
    queryFn: () => calendarApi.list({ show_completed: showCompleted }),
  })

  // Fetch upcoming events
  const { data: upcomingEvents } = useQuery<CalendarEvent[]>({
    queryKey: ['upcoming-events'],
    queryFn: () => calendarApi.getUpcoming(30),
  })

  // Fetch summary
  const { data: summary } = useQuery<CalendarSummary>({
    queryKey: ['calendar-summary'],
    queryFn: calendarApi.getSummary,
  })

  // Fetch market events
  const { data: marketEvents } = useQuery<MarketEvent[]>({
    queryKey: ['market-events'],
    queryFn: predictionsApi.getMarketEvents,
  })

  // Create event mutation
  const createMutation = useMutation({
    mutationFn: calendarApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['calendar-events'] })
      queryClient.invalidateQueries({ queryKey: ['upcoming-events'] })
      queryClient.invalidateQueries({ queryKey: ['calendar-summary'] })
      setShowAddEvent(false)
      toast({ title: 'Evenement cree', description: 'L\'evenement a ete ajoute.' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de creer l\'evenement.' })
    },
  })

  // Update event mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof calendarApi.update>[1] }) =>
      calendarApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['calendar-events'] })
      queryClient.invalidateQueries({ queryKey: ['upcoming-events'] })
      queryClient.invalidateQueries({ queryKey: ['calendar-summary'] })
      setEditingEvent(null)
      toast({ title: 'Evenement mis a jour' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de modifier l\'evenement.' })
    },
  })

  // Complete event mutation
  const completeMutation = useMutation({
    mutationFn: calendarApi.complete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['calendar-events'] })
      queryClient.invalidateQueries({ queryKey: ['upcoming-events'] })
      queryClient.invalidateQueries({ queryKey: ['calendar-summary'] })
      toast({ title: 'Evenement complete' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de completer l\'evenement.' })
    },
  })

  // Delete event mutation
  const deleteMutation = useMutation({
    mutationFn: calendarApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['calendar-events'] })
      queryClient.invalidateQueries({ queryKey: ['upcoming-events'] })
      queryClient.invalidateQueries({ queryKey: ['calendar-summary'] })
      toast({ title: 'Evenement supprime' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de supprimer l\'evenement.' })
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
            Gerez vos echeances et evenements financiers.
          </p>
        </div>
        <Button onClick={() => setShowAddEvent(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Nouvel evenement
        </Button>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid gap-4 md:grid-cols-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Evenements a venir
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
                Completes
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{summary.completed_events}</div>
            </CardContent>
          </Card>
        </div>
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
              Prochains evenements (30 jours)
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
          <Label htmlFor="show-completed">Afficher les completes</Label>
        </div>
      </div>

      {/* All Events */}
      {events && events.length > 0 ? (
        <div className="space-y-3">
          {events.map((event) => {
            const typeInfo = getEventTypeInfo(event.event_type)
            const overdue = isOverdue(event)

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
                        style={{ backgroundColor: `${typeInfo?.color}20` }}
                      >
                        <span style={{ color: typeInfo?.color }}>
                          {eventTypeIcons[event.event_type]}
                        </span>
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className={`font-medium ${event.is_completed ? 'line-through' : ''}`}>
                            {event.title}
                          </h3>
                          {event.is_recurring && (
                            <Badge variant="outline" className="text-xs">
                              <RefreshCw className="h-3 w-3 mr-1" />
                              Recurrent
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
                            title="Marquer comme complete"
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
                            if (confirm('Supprimer cet evenement ?')) {
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
              <h2 className="text-xl font-semibold">Aucun evenement</h2>
              <p className="text-muted-foreground max-w-md mx-auto">
                Ajoutez des evenements pour suivre vos dividendes, loyers et echeances.
              </p>
              <Button onClick={() => setShowAddEvent(true)}>
                <Plus className="h-4 w-4 mr-2" />
                Creer un evenement
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
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {editingEvent ? 'Modifier l\'evenement' : 'Nouvel evenement'}
            </DialogTitle>
            <DialogDescription>
              {editingEvent
                ? 'Modifiez les informations de l\'evenement.'
                : 'Ajoutez un nouvel evenement a votre calendrier.'}
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
                    <SelectValue placeholder="Selectionnez un type" />
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
                  placeholder="Details de l'evenement..."
                  rows={2}
                />
              </div>

              <div className="flex items-center gap-2">
                <Checkbox
                  id="is_recurring"
                  name="is_recurring"
                  defaultChecked={editingEvent?.is_recurring || false}
                />
                <Label htmlFor="is_recurring">Evenement recurrent</Label>
              </div>

              <div className="space-y-2">
                <Label htmlFor="recurrence_rule">Frequence de recurrence</Label>
                <Select
                  name="recurrence_rule"
                  defaultValue={editingEvent?.recurrence_rule || ''}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Selectionnez une frequence" />
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
                {editingEvent ? 'Enregistrer' : 'Creer'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
