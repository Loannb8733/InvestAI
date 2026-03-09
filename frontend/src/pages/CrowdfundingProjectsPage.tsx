import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
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
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { formatCurrency } from '@/lib/utils'
import { crowdfundingApi, portfoliosApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import { useToast } from '@/hooks/use-toast'
import { Textarea } from '@/components/ui/textarea'
import { Plus, Trash2, Edit, Loader2, FolderOpen, Upload, FileText, Download, X, Banknote } from 'lucide-react'
import type { CrowdfundingProject, ProjectStatus, RepaymentType, PaymentType } from '@/types/crowdfunding'

const STATUS_COLORS: Record<ProjectStatus, string> = {
  funding: 'bg-yellow-500/10 text-yellow-500',
  active: 'bg-green-500/10 text-green-500',
  completed: 'bg-blue-500/10 text-blue-500',
  delayed: 'bg-orange-500/10 text-orange-500',
  defaulted: 'bg-red-500/10 text-red-500',
}

const STATUS_LABELS: Record<ProjectStatus, string> = {
  funding: 'En cours de levée',
  active: 'Actif',
  completed: 'Terminé',
  delayed: 'En retard',
  defaulted: 'Défaut',
}

const PLATFORMS = ['Anaxago', 'Wiseed', 'Raizers', 'Homunity', 'ClubFunding', 'Fundimmo', 'October', 'Enerfip', 'Lendopolis', 'Tokimo', 'Autre']

const PAYMENT_TYPE_LABELS: Record<PaymentType, string> = {
  interest: 'Intérêts',
  capital: 'Capital',
  both: 'Intérêts + Capital',
}

interface RepaymentForm {
  payment_date: string
  amount: string
  payment_type: PaymentType
  notes: string
}

const emptyRepaymentForm: RepaymentForm = {
  payment_date: new Date().toISOString().split('T')[0],
  amount: '',
  payment_type: 'interest',
  notes: '',
}

interface ProjectForm {
  platform: string
  project_name: string
  invested_amount: string
  annual_rate: string
  duration_months: string
  repayment_type: RepaymentType
  start_date: string
  estimated_end_date: string
  status: ProjectStatus
  description: string
  project_url: string
}

const emptyForm: ProjectForm = {
  platform: '',
  project_name: '',
  invested_amount: '',
  annual_rate: '',
  duration_months: '',
  repayment_type: 'in_fine',
  start_date: '',
  estimated_end_date: '',
  status: 'active',
  description: '',
  project_url: '',
}

export default function CrowdfundingProjectsPage() {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [form, setForm] = useState(emptyForm)
  const [files, setFiles] = useState<File[]>([])
  const [uploadingDocs, setUploadingDocs] = useState(false)
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [repaymentDialogOpen, setRepaymentDialogOpen] = useState(false)
  const [repaymentProjectId, setRepaymentProjectId] = useState<string | null>(null)
  const [repaymentForm, setRepaymentForm] = useState(emptyRepaymentForm)

  const { data: projects = [], isLoading } = useQuery<CrowdfundingProject[]>({
    queryKey: queryKeys.crowdfunding.list,
    queryFn: crowdfundingApi.list,
  })

  const { data: portfolios } = useQuery({
    queryKey: queryKeys.portfolios.list(),
    queryFn: portfoliosApi.list,
  })

  const portfolioId = portfolios?.[0]?.id

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.crowdfunding.all })
  }

  const uploadFiles = async (projectId: string) => {
    if (files.length === 0) return
    setUploadingDocs(true)
    try {
      await crowdfundingApi.uploadDocuments(projectId, files)
      toast({ title: `${files.length} document(s) uploadé(s) — audit lancé` })
    } catch {
      toast({ title: 'Erreur lors de l\'upload des documents', variant: 'destructive' })
    } finally {
      setUploadingDocs(false)
      setFiles([])
    }
  }

  const createMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => crowdfundingApi.create(data),
    onSuccess: async (project: CrowdfundingProject) => {
      await uploadFiles(project.id)
      invalidate()
      setDialogOpen(false)
      setForm(emptyForm)
      toast({ title: 'Projet créé' })
    },
    onError: () => toast({ title: 'Erreur lors de la création', variant: 'destructive' }),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, unknown> }) =>
      crowdfundingApi.update(id, data),
    onSuccess: async (_: unknown, variables: { id: string; data: Record<string, unknown> }) => {
      await uploadFiles(variables.id)
      invalidate()
      setDialogOpen(false)
      setEditingId(null)
      setForm(emptyForm)
      toast({ title: 'Projet mis à jour' })
    },
    onError: () => toast({ title: 'Erreur lors de la mise à jour', variant: 'destructive' }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => crowdfundingApi.delete(id),
    onSuccess: () => {
      invalidate()
      setDeletingId(null)
      toast({ title: 'Projet supprimé' })
    },
    onError: () => toast({ title: 'Erreur lors de la suppression', variant: 'destructive' }),
  })

  const createRepaymentMutation = useMutation({
    mutationFn: ({ projectId, data }: { projectId: string; data: { payment_date: string; amount: number; payment_type: PaymentType; notes?: string } }) =>
      crowdfundingApi.createRepayment(projectId, data),
    onSuccess: () => {
      invalidate()
      setRepaymentDialogOpen(false)
      setRepaymentProjectId(null)
      setRepaymentForm(emptyRepaymentForm)
      toast({ title: 'Versement enregistré' })
    },
    onError: () => toast({ title: 'Erreur lors de l\'enregistrement', variant: 'destructive' }),
  })

  const deleteRepaymentMutation = useMutation({
    mutationFn: ({ projectId, repaymentId }: { projectId: string; repaymentId: string }) =>
      crowdfundingApi.deleteRepayment(projectId, repaymentId),
    onSuccess: () => {
      invalidate()
      toast({ title: 'Versement supprimé' })
    },
    onError: () => toast({ title: 'Erreur lors de la suppression', variant: 'destructive' }),
  })

  const handleRepaymentSubmit = () => {
    if (!repaymentProjectId || !repaymentForm.amount) return
    createRepaymentMutation.mutate({
      projectId: repaymentProjectId,
      data: {
        payment_date: repaymentForm.payment_date,
        amount: parseFloat(repaymentForm.amount),
        payment_type: repaymentForm.payment_type,
        notes: repaymentForm.notes || undefined,
      },
    })
  }

  const handleSubmit = () => {
    const payload: Record<string, unknown> = {
      platform: form.platform,
      project_name: form.project_name,
      invested_amount: parseFloat(form.invested_amount),
      annual_rate: parseFloat(form.annual_rate),
      duration_months: parseInt(form.duration_months),
      repayment_type: form.repayment_type,
      status: form.status,
    }
    if (form.start_date) payload.start_date = form.start_date
    if (form.estimated_end_date) payload.estimated_end_date = form.estimated_end_date
    if (form.description) payload.description = form.description
    if (form.project_url) payload.project_url = form.project_url

    if (editingId) {
      updateMutation.mutate({ id: editingId, data: payload })
    } else {
      payload.portfolio_id = portfolioId
      createMutation.mutate(payload)
    }
  }

  const openEdit = (p: CrowdfundingProject) => {
    setEditingId(p.id)
    setForm({
      platform: p.platform,
      project_name: p.project_name || '',
      invested_amount: String(p.invested_amount),
      annual_rate: String(p.annual_rate),
      duration_months: String(p.duration_months),
      repayment_type: p.repayment_type,
      start_date: p.start_date || '',
      estimated_end_date: p.estimated_end_date || '',
      status: p.status,
      description: p.description || '',
      project_url: p.project_url || '',
    })
    setDialogOpen(true)
  }

  const filtered = statusFilter === 'all'
    ? projects
    : projects.filter((p) => p.status === statusFilter)

  const isSubmitting = createMutation.isPending || updateMutation.isPending

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Mes Projets</h1>
          <p className="text-muted-foreground">
            Gérez vos investissements crowdfunding
          </p>
        </div>
        <Dialog
          open={dialogOpen}
          onOpenChange={(open) => {
            setDialogOpen(open)
            if (!open) {
              setEditingId(null)
              setForm(emptyForm)
              setFiles([])
            }
          }}
        >
          <DialogTrigger asChild>
            <Button disabled={!portfolioId}>
              <Plus className="h-4 w-4 mr-2" />
              Ajouter un projet
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{editingId ? 'Modifier le projet' : 'Nouveau projet'}</DialogTitle>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <div className="grid gap-2">
                <Label>Plateforme</Label>
                <Select value={form.platform} onValueChange={(v) => setForm({ ...form, platform: v })}>
                  <SelectTrigger>
                    <SelectValue placeholder="Choisir..." />
                  </SelectTrigger>
                  <SelectContent>
                    {PLATFORMS.map((p) => (
                      <SelectItem key={p} value={p}>{p}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label>Nom du projet</Label>
                <Input
                  value={form.project_name}
                  onChange={(e) => setForm({ ...form, project_name: e.target.value })}
                  placeholder="Résidence Les Lilas - Paris 19"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="grid gap-2">
                  <Label>Montant investi (€)</Label>
                  <Input
                    type="number"
                    value={form.invested_amount}
                    onChange={(e) => setForm({ ...form, invested_amount: e.target.value })}
                    placeholder="500"
                  />
                </div>
                <div className="grid gap-2">
                  <Label>Taux annuel (%)</Label>
                  <Input
                    type="number"
                    step="0.1"
                    value={form.annual_rate}
                    onChange={(e) => setForm({ ...form, annual_rate: e.target.value })}
                    placeholder="9.5"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="grid gap-2">
                  <Label>Durée (mois)</Label>
                  <Input
                    type="number"
                    value={form.duration_months}
                    onChange={(e) => setForm({ ...form, duration_months: e.target.value })}
                    placeholder="24"
                  />
                </div>
                <div className="grid gap-2">
                  <Label>Remboursement</Label>
                  <Select
                    value={form.repayment_type}
                    onValueChange={(v) => setForm({ ...form, repayment_type: v as 'in_fine' | 'amortizable' })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="in_fine">In Fine</SelectItem>
                      <SelectItem value="amortizable">Amortissable</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="grid gap-2">
                  <Label>Date début</Label>
                  <Input
                    type="date"
                    value={form.start_date}
                    onChange={(e) => setForm({ ...form, start_date: e.target.value })}
                  />
                </div>
                <div className="grid gap-2">
                  <Label>Date fin estimée</Label>
                  <Input
                    type="date"
                    value={form.estimated_end_date}
                    onChange={(e) => setForm({ ...form, estimated_end_date: e.target.value })}
                  />
                </div>
              </div>
              <div className="grid gap-2">
                <Label>Statut</Label>
                <Select
                  value={form.status}
                  onValueChange={(v) => setForm({ ...form, status: v as ProjectStatus })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(STATUS_LABELS).map(([k, v]) => (
                      <SelectItem key={k} value={k}>{v}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label>URL du projet (optionnel)</Label>
                <Input
                  value={form.project_url}
                  onChange={(e) => setForm({ ...form, project_url: e.target.value })}
                  placeholder="https://..."
                />
              </div>
              {/* Documents upload */}
              <div className="grid gap-2">
                <Label>Documents PDF (optionnel)</Label>
                <div
                  className="border-2 border-dashed rounded-lg p-4 text-center cursor-pointer hover:border-primary/50 transition-colors"
                  onClick={() => document.getElementById('pdf-upload')?.click()}
                >
                  <Upload className="h-6 w-6 mx-auto text-muted-foreground mb-2" />
                  <p className="text-sm text-muted-foreground">
                    Cliquez pour ajouter des PDFs (max 5, 10 MB chacun)
                  </p>
                  <input
                    id="pdf-upload"
                    type="file"
                    accept=".pdf"
                    multiple
                    className="hidden"
                    onChange={(e) => {
                      const newFiles = Array.from(e.target.files || [])
                      setFiles((prev) => [...prev, ...newFiles].slice(0, 5))
                      e.target.value = ''
                    }}
                  />
                </div>
                {files.length > 0 && (
                  <div className="space-y-1">
                    {files.map((f, i) => (
                      <div key={i} className="flex items-center gap-2 text-sm bg-muted rounded px-2 py-1">
                        <FileText className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                        <span className="truncate flex-1">{f.name}</span>
                        <span className="text-muted-foreground shrink-0">
                          {(f.size / 1024).toFixed(0)} KB
                        </span>
                        <button
                          type="button"
                          onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
                          className="text-muted-foreground hover:text-destructive"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <Button
                onClick={handleSubmit}
                disabled={!form.platform || !form.project_name || !form.invested_amount || !form.annual_rate || !form.duration_months || isSubmitting || uploadingDocs}
              >
                {(isSubmitting || uploadingDocs) && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                {editingId ? 'Modifier' : 'Créer'}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* Filter */}
      <div className="flex gap-2">
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-48">
            <SelectValue placeholder="Filtrer par statut" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tous les statuts</SelectItem>
            {Object.entries(STATUS_LABELS).map(([k, v]) => (
              <SelectItem key={k} value={k}>{v}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Projects list */}
      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <FolderOpen className="h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-muted-foreground">Aucun projet trouvé</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filtered.map((p) => (
            <Card key={p.id}>
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <CardTitle className="text-base truncate">
                      {p.project_name || p.platform}
                    </CardTitle>
                    <p className="text-xs text-muted-foreground mt-1">{p.platform}</p>
                  </div>
                  <Badge className={STATUS_COLORS[p.status]}>{STATUS_LABELS[p.status]}</Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <p className="text-muted-foreground">Montant</p>
                    <p className="font-medium">{formatCurrency(p.invested_amount)}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Taux</p>
                    <p className="font-medium">{p.annual_rate}% / an</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Durée</p>
                    <p className="font-medium">{p.duration_months} mois</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Type</p>
                    <p className="font-medium">
                      {p.repayment_type === 'in_fine' ? 'In Fine' : 'Amortissable'}
                    </p>
                  </div>
                </div>

                {/* Progress bar */}
                {p.progress_percent !== null && p.status === 'active' && (
                  <div>
                    <div className="flex justify-between text-xs text-muted-foreground mb-1">
                      <span>Progression</span>
                      <span>{p.progress_percent}%</span>
                    </div>
                    <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-primary rounded-full transition-all"
                        style={{ width: `${Math.min(100, p.progress_percent)}%` }}
                      />
                    </div>
                  </div>
                )}

                {p.projected_total_interest !== null && (
                  <div className="text-sm">
                    <span className="text-muted-foreground">Intérêts projetés : </span>
                    <span className="font-medium text-green-500">
                      {formatCurrency(p.projected_total_interest)}
                    </span>
                  </div>
                )}

                {/* Documents */}
                {p.documents && p.documents.length > 0 && (
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground font-medium">
                      {p.documents.length} document(s)
                    </p>
                    {p.documents.map((doc) => (
                      <div key={doc.id} className="flex items-center gap-1.5 text-xs">
                        <FileText className="h-3 w-3 text-muted-foreground shrink-0" />
                        <span className="truncate flex-1">{doc.file_name}</span>
                        <button
                          onClick={async () => {
                            try {
                              const blob = await crowdfundingApi.downloadDocument(doc.id)
                              const url = URL.createObjectURL(blob)
                              const a = document.createElement('a')
                              a.href = url
                              a.download = doc.file_name
                              a.click()
                              URL.revokeObjectURL(url)
                            } catch {
                              toast({ title: 'Erreur de téléchargement', variant: 'destructive' })
                            }
                          }}
                          className="text-muted-foreground hover:text-primary shrink-0"
                        >
                          <Download className="h-3 w-3" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                {/* Repayments summary */}
                <div className="border-t pt-3 space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Reçu</span>
                    <span>
                      <span className="font-medium text-green-500">{formatCurrency(p.total_received)}</span>
                      <span className="text-muted-foreground"> / {formatCurrency(p.projected_total_interest ?? 0)}</span>
                    </span>
                  </div>
                  {p.repayments && p.repayments.length > 0 && (
                    <div className="space-y-1">
                      {p.repayments.slice(0, 3).map((r) => (
                        <div key={r.id} className="flex items-center justify-between text-xs group">
                          <span className="text-muted-foreground">
                            {new Date(r.payment_date).toLocaleDateString('fr-FR')} — {PAYMENT_TYPE_LABELS[r.payment_type]}
                          </span>
                          <span className="flex items-center gap-1">
                            <span className="font-medium text-green-500">+{formatCurrency(r.amount)}</span>
                            <button
                              onClick={() => deleteRepaymentMutation.mutate({ projectId: p.id, repaymentId: r.id })}
                              className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive transition-opacity"
                            >
                              <X className="h-3 w-3" />
                            </button>
                          </span>
                        </div>
                      ))}
                      {p.repayments.length > 3 && (
                        <p className="text-xs text-muted-foreground">+ {p.repayments.length - 3} autre(s)</p>
                      )}
                    </div>
                  )}
                </div>

                <div className="flex gap-2 pt-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setRepaymentProjectId(p.id)
                      setRepaymentForm(emptyRepaymentForm)
                      setRepaymentDialogOpen(true)
                    }}
                  >
                    <Banknote className="h-3.5 w-3.5 mr-1" />
                    + Versement
                  </Button>
                  <Button variant="outline" size="sm" className="flex-1" onClick={() => openEdit(p)}>
                    <Edit className="h-3.5 w-3.5 mr-1" />
                    Modifier
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    onClick={() => setDeletingId(p.id)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Delete confirmation */}
      <AlertDialog open={!!deletingId} onOpenChange={() => setDeletingId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Supprimer ce projet ?</AlertDialogTitle>
            <AlertDialogDescription>
              Cette action est irréversible. Le projet sera définitivement supprimé
              de votre portefeuille.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annuler</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deletingId && deleteMutation.mutate(deletingId)}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Supprimer
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Repayment dialog */}
      <Dialog
        open={repaymentDialogOpen}
        onOpenChange={(open) => {
          setRepaymentDialogOpen(open)
          if (!open) {
            setRepaymentProjectId(null)
            setRepaymentForm(emptyRepaymentForm)
          }
        }}
      >
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Enregistrer un versement</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label>Date</Label>
              <Input
                type="date"
                value={repaymentForm.payment_date}
                onChange={(e) => setRepaymentForm({ ...repaymentForm, payment_date: e.target.value })}
              />
            </div>
            <div className="grid gap-2">
              <Label>Montant (€)</Label>
              <Input
                type="number"
                step="0.01"
                value={repaymentForm.amount}
                onChange={(e) => setRepaymentForm({ ...repaymentForm, amount: e.target.value })}
                placeholder="6.72"
              />
            </div>
            <div className="grid gap-2">
              <Label>Type</Label>
              <Select
                value={repaymentForm.payment_type}
                onValueChange={(v) => setRepaymentForm({ ...repaymentForm, payment_type: v as PaymentType })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(PAYMENT_TYPE_LABELS).map(([k, v]) => (
                    <SelectItem key={k} value={k}>{v}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label>Notes (optionnel)</Label>
              <Textarea
                value={repaymentForm.notes}
                onChange={(e) => setRepaymentForm({ ...repaymentForm, notes: e.target.value })}
                placeholder="Coupon mensuel mars 2026..."
                rows={2}
              />
            </div>
            <Button
              onClick={handleRepaymentSubmit}
              disabled={!repaymentForm.payment_date || !repaymentForm.amount || createRepaymentMutation.isPending}
            >
              {createRepaymentMutation.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Enregistrer
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
