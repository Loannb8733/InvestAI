import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { formatCurrency } from '@/lib/utils'
import { alertsApi, assetsApi } from '@/services/api'
import {
  Bell,
  BellOff,
  Plus,
  Trash2,
  RefreshCw,
  Loader2,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Clock,
  CheckCircle,
} from 'lucide-react'
import { useToast } from '@/hooks/use-toast'
import { AssetIconCompact } from '@/components/ui/asset-icon'

interface Alert {
  id: string
  asset_id: string | null
  name: string
  condition: string
  threshold: number
  currency: string
  is_active: boolean
  triggered_at: string | null
  triggered_count: number
  notify_email: boolean
  notify_in_app: boolean
  created_at: string
  asset_symbol: string | null
  asset_name: string | null
}

interface AlertCondition {
  value: string
  label: string
  description: string
}

interface AlertSummary {
  total_alerts: number
  active_alerts: number
  triggered_today: number
  total_triggers: number
}

interface Asset {
  id: string
  symbol: string
  name: string
  asset_type: string
}

export default function AlertsPage() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [, setSelectedAlert] = useState<Alert | null>(null)
  const [formData, setFormData] = useState({
    asset_id: '',
    name: '',
    condition: '',
    threshold: '',
    currency: 'EUR',
    notify_email: true,
    notify_in_app: true,
  })

  const { data: alerts, isLoading: loadingAlerts } = useQuery<Alert[]>({
    queryKey: ['alerts'],
    queryFn: () => alertsApi.list(),
  })

  const { data: conditions } = useQuery<AlertCondition[]>({
    queryKey: ['alert-conditions'],
    queryFn: alertsApi.listConditions,
  })

  const { data: summary } = useQuery<AlertSummary>({
    queryKey: ['alert-summary'],
    queryFn: alertsApi.getSummary,
  })

  const { data: assets } = useQuery<Asset[]>({
    queryKey: ['assets'],
    queryFn: () => assetsApi.list(),
  })

  const createMutation = useMutation({
    mutationFn: alertsApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
      queryClient.invalidateQueries({ queryKey: ['alert-summary'] })
      setIsCreateOpen(false)
      resetForm()
      toast({ title: 'Alerte créée avec succès' })
    },
    onError: () => {
      toast({ title: 'Erreur lors de la création de l\'alerte', variant: 'destructive' })
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof alertsApi.update>[1] }) => alertsApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
      queryClient.invalidateQueries({ queryKey: ['alert-summary'] })
      setSelectedAlert(null)
      toast({ title: 'Alerte mise à jour' })
    },
    onError: () => {
      toast({ title: 'Erreur lors de la mise à jour', variant: 'destructive' })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: alertsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
      queryClient.invalidateQueries({ queryKey: ['alert-summary'] })
      toast({ title: 'Alerte supprimée' })
    },
    onError: () => {
      toast({ title: 'Erreur lors de la suppression', variant: 'destructive' })
    },
  })

  const checkMutation = useMutation({
    mutationFn: alertsApi.checkAlerts,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
      queryClient.invalidateQueries({ queryKey: ['alert-summary'] })
      if (data.length > 0) {
        toast({ title: `${data.length} alerte(s) déclenchée(s)` })
      } else {
        toast({ title: 'Aucune alerte déclenchée' })
      }
    },
    onError: () => {
      toast({ title: 'Erreur lors de la vérification', variant: 'destructive' })
    },
  })

  const resetForm = () => {
    setFormData({
      asset_id: '',
      name: '',
      condition: '',
      threshold: '',
      currency: 'EUR',
      notify_email: true,
      notify_in_app: true,
    })
  }

  const handleCreate = () => {
    if (!formData.asset_id || !formData.name || !formData.condition || !formData.threshold) {
      toast({ title: 'Veuillez remplir tous les champs obligatoires', variant: 'destructive' })
      return
    }

    createMutation.mutate({
      asset_id: formData.asset_id,
      name: formData.name,
      condition: formData.condition,
      threshold: parseFloat(formData.threshold),
      currency: formData.currency,
      notify_email: formData.notify_email,
      notify_in_app: formData.notify_in_app,
    })
  }

  const handleToggleActive = (alert: Alert) => {
    updateMutation.mutate({
      id: alert.id,
      data: { is_active: !alert.is_active },
    })
  }

  const getConditionLabel = (conditionValue: string) => {
    const condition = conditions?.find((c) => c.value === conditionValue)
    return condition?.label || conditionValue
  }

  const getConditionIcon = (conditionValue: string) => {
    if (conditionValue.includes('up') || conditionValue.includes('above')) {
      return <TrendingUp className="h-4 w-4 text-green-500" />
    }
    return <TrendingDown className="h-4 w-4 text-red-500" />
  }

  if (loadingAlerts) {
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
          <h1 className="text-3xl font-bold">Alertes</h1>
          <p className="text-muted-foreground">
            Configurez des alertes sur vos actifs
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => checkMutation.mutate()}
            disabled={checkMutation.isPending}
          >
            {checkMutation.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4 mr-2" />
            )}
            Vérifier
          </Button>
          <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="h-4 w-4 mr-2" />
                Nouvelle alerte
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-[425px]">
              <DialogHeader>
                <DialogTitle>Créer une alerte</DialogTitle>
                <DialogDescription>
                  Configurez une alerte pour être notifié des variations de prix
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-4 py-4">
                <div className="grid gap-2">
                  <Label htmlFor="name">Nom de l'alerte</Label>
                  <Input
                    id="name"
                    placeholder="Ex: Alerte BTC hausse"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="asset">Actif</Label>
                  <Select
                    value={formData.asset_id}
                    onValueChange={(value) => setFormData({ ...formData, asset_id: value })}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Sélectionner un actif" />
                    </SelectTrigger>
                    <SelectContent>
                      {assets?.map((asset) => (
                        <SelectItem key={asset.id} value={asset.id}>
                          {asset.symbol} - {asset.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="condition">Condition</Label>
                  <Select
                    value={formData.condition}
                    onValueChange={(value) => setFormData({ ...formData, condition: value })}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Sélectionner une condition" />
                    </SelectTrigger>
                    <SelectContent>
                      {conditions?.map((condition) => (
                        <SelectItem key={condition.value} value={condition.value}>
                          {condition.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="threshold">Seuil</Label>
                  <div className="flex gap-2">
                    <Input
                      id="threshold"
                      type="number"
                      step="0.01"
                      placeholder="Ex: 50000"
                      value={formData.threshold}
                      onChange={(e) => setFormData({ ...formData, threshold: e.target.value })}
                      className="flex-1"
                    />
                    <Select
                      value={formData.currency}
                      onValueChange={(value) => setFormData({ ...formData, currency: value })}
                    >
                      <SelectTrigger className="w-24">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="EUR">EUR</SelectItem>
                        <SelectItem value="USD">USD</SelectItem>
                        <SelectItem value="%">%</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <Label htmlFor="notify_email">Notification email</Label>
                  <Switch
                    id="notify_email"
                    checked={formData.notify_email}
                    onCheckedChange={(checked) => setFormData({ ...formData, notify_email: checked })}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <Label htmlFor="notify_in_app">Notification in-app</Label>
                  <Switch
                    id="notify_in_app"
                    checked={formData.notify_in_app}
                    onCheckedChange={(checked) => setFormData({ ...formData, notify_in_app: checked })}
                  />
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setIsCreateOpen(false)}>
                  Annuler
                </Button>
                <Button onClick={handleCreate} disabled={createMutation.isPending}>
                  {createMutation.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                  Créer
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total alertes</CardTitle>
              <Bell className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{summary.total_alerts}</div>
              <p className="text-xs text-muted-foreground">
                Alertes configurées
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Actives</CardTitle>
              <CheckCircle className="h-4 w-4 text-green-500" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-green-500">{summary.active_alerts}</div>
              <p className="text-xs text-muted-foreground">
                Alertes en surveillance
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Aujourd'hui</CardTitle>
              <Clock className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-orange-500">{summary.triggered_today}</div>
              <p className="text-xs text-muted-foreground">
                Déclenchées aujourd'hui
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total déclenché</CardTitle>
              <AlertTriangle className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{summary.total_triggers}</div>
              <p className="text-xs text-muted-foreground">
                Nombre total de déclenchements
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Alerts List */}
      <Card>
        <CardHeader>
          <CardTitle>Mes alertes</CardTitle>
          <CardDescription>
            Gérez vos alertes de prix et de performance
          </CardDescription>
        </CardHeader>
        <CardContent>
          {alerts && alerts.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nom</TableHead>
                  <TableHead>Actif</TableHead>
                  <TableHead>Condition</TableHead>
                  <TableHead>Seuil</TableHead>
                  <TableHead>Déclenchements</TableHead>
                  <TableHead>Statut</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {alerts.map((alert) => (
                  <TableRow key={alert.id}>
                    <TableCell className="font-medium">{alert.name}</TableCell>
                    <TableCell>
                      {alert.asset_symbol && (
                        <AssetIconCompact
                          symbol={alert.asset_symbol}
                          name={alert.asset_name || undefined}
                          assetType="crypto"
                          size={32}
                        />
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {getConditionIcon(alert.condition)}
                        <span>{getConditionLabel(alert.condition)}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      {alert.condition.includes('percent') || alert.condition.includes('change')
                        ? `${alert.threshold}%`
                        : formatCurrency(alert.threshold, alert.currency)}
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary">
                        {alert.triggered_count}x
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={alert.is_active ? 'default' : 'secondary'}>
                        {alert.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleToggleActive(alert)}
                          title={alert.is_active ? 'Désactiver' : 'Activer'}
                        >
                          {alert.is_active ? (
                            <BellOff className="h-4 w-4" />
                          ) : (
                            <Bell className="h-4 w-4" />
                          )}
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => deleteMutation.mutate(alert.id)}
                          className="text-destructive hover:text-destructive"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <div className="text-center py-12">
              <Bell className="h-16 w-16 mx-auto text-muted-foreground" />
              <h2 className="text-xl font-semibold mt-4">Aucune alerte</h2>
              <p className="text-muted-foreground mt-2 max-w-md mx-auto">
                Créez votre première alerte pour être notifié des variations de prix de vos actifs.
              </p>
              <Button className="mt-4" onClick={() => setIsCreateOpen(true)}>
                <Plus className="h-4 w-4 mr-2" />
                Créer une alerte
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Notification Settings Info */}
      <Card>
        <CardHeader>
          <CardTitle>Types d'alertes disponibles</CardTitle>
          <CardDescription>
            Choisissez parmi différentes conditions de déclenchement
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {conditions?.map((condition) => (
              <div
                key={condition.value}
                className="p-4 rounded-lg border bg-muted/50"
              >
                <div className="flex items-center gap-2 mb-2">
                  {getConditionIcon(condition.value)}
                  <span className="font-medium">{condition.label}</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  {condition.description}
                </p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
