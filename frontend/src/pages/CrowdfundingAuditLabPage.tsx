import { useState, useCallback } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useDropzone } from 'react-dropzone'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import SpotlightGroup from '@/components/ui/spotlight-group'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { formatCurrency } from '@/lib/utils'
import { crowdfundingApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import {
  ShieldCheck,
  Upload,
  FileText,
  X,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  TrendingUp,
  MapPin,
  Building2,
  Clock,
  Banknote,
  Shield,
  ChevronDown,
  ChevronUp,
  Calculator,
  Percent,
  Wallet,
  Calendar,
  Link2,
} from 'lucide-react'
import { ResponsiveRadar } from '@nivo/radar'
import { useNivoTheme } from '@/components/charts/nivo-theme'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { CrowdfundingDashboard, ProjectAudit } from '@/types/crowdfunding'
import DiversificationRadar from '@/components/analytics/DiversificationRadar'

const VERDICT_CONFIG = {
  INVESTIR: { color: 'bg-gain text-white', text: 'Investir', icon: CheckCircle2 },
  VIGILANCE: { color: 'bg-warning text-foreground', text: 'Vigilance', icon: AlertTriangle },
  NE_PAS_INVESTIR: { color: 'bg-loss text-white', text: 'Ne pas investir', icon: AlertTriangle },
} as const

function VerdictBadge({ verdict }: { verdict: string }) {
  const config = VERDICT_CONFIG[verdict as keyof typeof VERDICT_CONFIG] || VERDICT_CONFIG.VIGILANCE
  const Icon = config.icon
  return (
    <Badge className={`${config.color} text-sm px-3 py-1`}>
      <Icon className="h-4 w-4 mr-1" strokeWidth={1.5} />
      {config.text}
    </Badge>
  )
}

function AuditResults({ audit }: { audit: ProjectAudit }) {
  const { theme, color } = useNivoTheme()
  const radarData = [
    { subject: 'Opérateur', score: audit.score_operator ?? 0 },
    { subject: 'Localisation', score: audit.score_location ?? 0 },
    { subject: 'Garanties', score: audit.score_guarantees ?? 0 },
    { subject: 'Rendement/Risque', score: audit.score_risk_return ?? 0 },
    { subject: 'Administratif', score: audit.score_admin ?? 0 },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-2xl font-serif font-medium">{audit.project_name || 'Projet analysé'}</h2>
          <div className="flex items-center gap-3 mt-1 text-muted-foreground">
            {audit.operator && (
              <span className="flex items-center gap-1">
                <Building2 className="h-4 w-4" />
                {audit.operator}
              </span>
            )}
            {audit.location && (
              <span className="flex items-center gap-1">
                <MapPin className="h-4 w-4" />
                {audit.location}
              </span>
            )}
          </div>
        </div>
        <VerdictBadge verdict={audit.verdict} />
      </div>

      {/* KPI Grid */}
      <SpotlightGroup className="grid gap-4 md:grid-cols-3 lg:grid-cols-6">
        {[
          { label: 'TRI', value: audit.tri != null ? `${audit.tri}%` : '—', icon: TrendingUp },
          { label: 'Durée', value: audit.duration_min && audit.duration_max ? `${audit.duration_min}-${audit.duration_max} mois` : audit.duration_max ? `${audit.duration_max} mois` : '—', icon: Clock },
          { label: 'Collecte', value: audit.collection_amount != null ? formatCurrency(audit.collection_amount) : '—', icon: Banknote },
          { label: 'Marge', value: audit.margin_percent != null ? `${audit.margin_percent}%` : '—', icon: TrendingUp },
          { label: 'LTV', value: audit.ltv != null ? `${audit.ltv}%` : '—', icon: Building2 },
          { label: 'LTC', value: audit.ltc != null ? `${audit.ltc}%` : '—', icon: Building2 },
        ].map((kpi) => (
          <Card key={kpi.label} elevation="raised" className="spot-card">
            <CardContent className="pt-4 pb-3 px-4">
              <div className="flex items-center gap-2 text-muted-foreground text-xs mb-1">
                <kpi.icon className="h-3 w-3" />
                {kpi.label}
              </div>
              <p className="text-lg font-bold">{kpi.value}</p>
            </CardContent>
          </Card>
        ))}
      </SpotlightGroup>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Radar Chart */}
        <Card elevation="raised">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              Score de Robustesse
              {audit.risk_score != null && (
                <Badge variant="outline" className="text-lg">
                  {audit.risk_score}/10
                </Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[280px]">
              <ResponsiveRadar
                data={radarData}
                keys={['score']}
                indexBy="subject"
                theme={theme}
                maxValue={10}
                margin={{ top: 28, right: 36, bottom: 28, left: 36 }}
                gridLevels={5}
                gridShape="circular"
                gridLabelOffset={12}
                colors={[color('--chart-2')]}
                fillOpacity={0.3}
                borderWidth={2}
                borderColor={{ from: 'color' }}
              />
            </div>
          </CardContent>
        </Card>

        {/* Verdict + Allocation */}
        <Card elevation="raised">
          <CardHeader>
            <CardTitle>Verdict & Allocation</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="flex items-center gap-4">
              <VerdictBadge verdict={audit.verdict} />
              {audit.suggested_investment != null && (
                <div>
                  <p className="text-sm text-muted-foreground">Allocation suggérée</p>
                  <p className="text-2xl font-serif font-medium text-accent">
                    {formatCurrency(audit.suggested_investment)}
                  </p>
                  <p className="text-xs text-muted-foreground">max 5% du capital</p>
                </div>
              )}
            </div>

            {/* Points Forts */}
            {audit.points_forts.length > 0 && (
              <div>
                <h4 className="text-sm font-medium text-gain mb-2">Points Forts</h4>
                <ul className="space-y-1">
                  {audit.points_forts.map((p, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm">
                      <CheckCircle2 className="h-4 w-4 text-gain mt-0.5 shrink-0" />
                      {p}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Points de Vigilance */}
            {audit.points_vigilance.length > 0 && (
              <div>
                <h4 className="text-sm font-medium text-warning mb-2">Points de Vigilance</h4>
                <ul className="space-y-1">
                  {audit.points_vigilance.map((p, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm">
                      <AlertTriangle className="h-4 w-4 text-warning mt-0.5 shrink-0" />
                      {p}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Red Flags */}
            {audit.red_flags.length > 0 && (
              <div className="rounded-lg border border-loss/30 bg-loss/5 p-3">
                <h4 className="text-sm font-medium text-loss mb-2 flex items-center gap-2">
                  Red Flags
                  <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-loss text-white text-xs font-bold">
                    {audit.red_flags.length}
                  </span>
                </h4>
                <ul className="space-y-1">
                  {audit.red_flags.map((p, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-loss">
                      <AlertTriangle className="h-4 w-4 text-loss mt-0.5 shrink-0" strokeWidth={1.5} />
                      {p}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Investment Simulation */}
      {audit.investment_simulation && (
        <Card elevation="raised">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Calculator className="h-5 w-5" />
              Simulation d'investissement
            </CardTitle>
          </CardHeader>
          <CardContent>
            {(() => {
              const sim = audit.investment_simulation
              return (
                <div className="space-y-4">
                  {/* Main figures */}
                  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                    <div className="bg-accent/10 border border-accent/20 rounded-lg p-4">
                      <div className="flex items-center gap-2 text-accent text-xs mb-1">
                        <Wallet className="h-3 w-3" />
                        Investissement suggéré
                      </div>
                      <p className="text-2xl font-serif font-medium text-accent">
                        {formatCurrency(sim.investment_amount)}
                      </p>
                      <p className="text-xs text-muted-foreground mt-1">
                        minimum 100 € obligatoire
                      </p>
                    </div>
                    <div className="bg-gain/10 border border-gain/20 rounded-lg p-4">
                      <div className="flex items-center gap-2 text-gain text-xs mb-1">
                        <TrendingUp className="h-3 w-3" />
                        Gain net estimé
                      </div>
                      <p className="text-2xl font-serif font-medium text-gain">
                        +{formatCurrency(sim.net_interest)}
                      </p>
                      <p className="text-xs text-muted-foreground mt-1">
                        après flat tax 30%
                      </p>
                    </div>
                    <div className="bg-accent/10 border border-accent/20 rounded-lg p-4">
                      <div className="flex items-center gap-2 text-accent text-xs mb-1">
                        <Banknote className="h-3 w-3" />
                        Total récupéré
                      </div>
                      <p className="text-2xl font-serif font-medium text-accent">
                        {formatCurrency(sim.total_at_end)}
                      </p>
                      <p className="text-xs text-muted-foreground mt-1">
                        capital + intérêts nets
                      </p>
                    </div>
                    <div className="bg-warning/10 border border-warning/20 rounded-lg p-4">
                      <div className="flex items-center gap-2 text-warning text-xs mb-1">
                        <Percent className="h-3 w-3" />
                        ROI net
                      </div>
                      <p className="text-2xl font-serif font-medium text-warning">
                        {sim.roi_net_percent}%
                      </p>
                      <p className="text-xs text-muted-foreground mt-1">
                        sur {sim.duration_months} mois
                      </p>
                    </div>
                  </div>

                  {/* Detail breakdown */}
                  <div className="bg-muted/30 rounded-lg p-4">
                    <h4 className="text-sm font-medium mb-3 flex items-center gap-2">
                      <Calendar className="h-4 w-4" />
                      Détail de la simulation
                    </h4>
                    <div className="grid gap-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Montant investi</span>
                        <span className="font-medium">{formatCurrency(sim.investment_amount)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Taux annuel (TRI)</span>
                        <span className="font-medium">{sim.tri_percent}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Durée estimée</span>
                        <span className="font-medium">{sim.duration_months} mois</span>
                      </div>
                      <div className="border-t border-muted pt-2 mt-1 flex justify-between">
                        <span className="text-muted-foreground">Intérêts bruts</span>
                        <span className="font-medium text-gain">+{formatCurrency(sim.gross_interest)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Flat tax (30%)</span>
                        <span className="font-medium text-loss">-{formatCurrency(sim.tax_amount)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Intérêts nets</span>
                        <span className="font-medium text-gain">+{formatCurrency(sim.net_interest)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Rendement mensuel brut</span>
                        <span className="font-medium">{formatCurrency(sim.monthly_gross_return)}/mois</span>
                      </div>
                      <div className="border-t border-muted pt-2 mt-1 flex justify-between text-base">
                        <span className="font-semibold">Total récupéré</span>
                        <span className="font-bold text-gain">{formatCurrency(sim.total_at_end)}</span>
                      </div>
                    </div>
                  </div>
                </div>
              )
            })()}
          </CardContent>
        </Card>
      )}

      {/* Guarantees Table */}
      {audit.guarantees.length > 0 && (
        <Card elevation="raised">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5" />
              Garanties
              {audit.admin_status && (
                <Badge variant="outline" className="ml-2">{audit.admin_status}</Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-muted-foreground text-left">
                    <th scope="col" className="pb-2 font-medium">Type</th>
                    <th scope="col" className="pb-2 font-medium">Rang</th>
                    <th scope="col" className="pb-2 font-medium">Description</th>
                    <th scope="col" className="pb-2 font-medium">Force</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.guarantees.map((g, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className="py-2 font-medium">{g.type}</td>
                      <td className="py-2">{g.rank || '—'}</td>
                      <td className="py-2 text-muted-foreground">{g.description}</td>
                      <td className="py-2">
                        <Badge
                          variant={g.strength === 'forte' ? 'default' : g.strength === 'moyenne' ? 'secondary' : 'destructive'}
                        >
                          {g.strength}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

export default function CrowdfundingAuditLabPage() {
  const [files, setFiles] = useState<File[]>([])
  const [currentAudit, setCurrentAudit] = useState<ProjectAudit | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  // Projet auquel rattacher l'analyse ('' = aucun)
  const [selectedProjectId, setSelectedProjectId] = useState<string>('')

  const { data: audits } = useQuery<ProjectAudit[]>({
    queryKey: queryKeys.crowdfunding.audits,
    queryFn: crowdfundingApi.listAudits,
  })

  // Projets de l'utilisateur (pour le rattachement optionnel de l'audit)
  const { data: dashboard } = useQuery<CrowdfundingDashboard>({
    queryKey: queryKeys.crowdfunding.dashboard,
    queryFn: crowdfundingApi.getDashboard,
  })
  const projects = dashboard?.projects ?? []

  const analyzeMutation = useMutation({
    mutationFn: (selectedFiles: File[]) =>
      crowdfundingApi.analyzeDocuments(selectedFiles, selectedProjectId || undefined),
    onSuccess: (data) => {
      setCurrentAudit(data)
      setFiles([])
      setSelectedProjectId('')
    },
  })

  // Nom du projet rattaché à l'audit affiché (si rattachement)
  const linkedProjectName = currentAudit?.project_id
    ? (() => {
        const p = projects.find((proj) => proj.id === currentAudit.project_id)
        return p ? p.project_name || p.platform : null
      })()
    : null

  const analyzeErrorMessage = analyzeMutation.isError
    ? (() => {
        const err = analyzeMutation.error as { response?: { data?: { detail?: string }; status?: number } }
        const detail = err?.response?.data?.detail
        if (detail) return detail
        if (err?.response?.status === 503) return 'Service IA indisponible — clé API Anthropic non configurée'
        return 'Analyse échouée — veuillez réessayer'
      })()
    : null

  const onDrop = useCallback((acceptedFiles: File[]) => {
    setFiles((prev) => [...prev, ...acceptedFiles].slice(0, 5))
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    maxFiles: 5,
    maxSize: 10 * 1024 * 1024,
  })

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-serif font-medium flex items-center gap-2">
          <ShieldCheck className="h-8 w-8" />
          Audit Lab
        </h1>
        <p className="text-muted-foreground">
          Analysez vos projets crowdfunding par IA — uploadez un DECK ou FICI pour obtenir un audit complet
        </p>
      </div>

      {/* Upload Zone */}
      {!currentAudit && (
        <Card elevation="raised">
          <CardContent className="pt-6">
            <div
              {...getRootProps()}
              className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
                isDragActive
                  ? 'border-accent bg-accent dark:bg-accent/20'
                  : 'border-muted-foreground/25 hover:border-muted-foreground/50'
              }`}
            >
              <input {...getInputProps()} />
              <Upload className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
              {isDragActive ? (
                <p className="text-accent font-medium">Déposez les fichiers ici...</p>
              ) : (
                <div>
                  <p className="font-medium">
                    Glissez-déposez vos PDFs ici, ou cliquez pour sélectionner
                  </p>
                  <p className="text-sm text-muted-foreground mt-1">
                    PDF uniquement — max 5 fichiers, 10 MB chacun
                  </p>
                </div>
              )}
            </div>

            {/* File List */}
            {files.length > 0 && (
              <div className="mt-4 space-y-2">
                {files.map((file, i) => (
                  <div
                    key={`${file.name}-${i}`}
                    className="flex items-center justify-between bg-muted/50 rounded-lg px-4 py-2"
                  >
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4 text-loss" />
                      <span className="text-sm font-medium">{file.name}</span>
                      <span className="text-xs text-muted-foreground">
                        ({(file.size / 1024 / 1024).toFixed(1)} MB)
                      </span>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => removeFile(i)}
                      className="h-6 w-6"
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                ))}

                {projects.length > 0 && (
                  <div className="mt-4 space-y-1.5">
                    <p className="text-sm font-medium flex items-center gap-1.5">
                      <Link2 className="h-4 w-4 text-muted-foreground" />
                      Rattacher à un projet (optionnel)
                    </p>
                    <Select
                      value={selectedProjectId || 'none'}
                      onValueChange={(v) => setSelectedProjectId(v === 'none' ? '' : v)}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Aucun projet" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">Aucun projet</SelectItem>
                        {projects.map((p) => (
                          <SelectItem key={p.id} value={p.id}>
                            {p.project_name || p.platform}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">
                      L'audit sera associé au projet sélectionné dans votre portefeuille.
                    </p>
                  </div>
                )}

                <Button
                  className="w-full mt-4"
                  size="lg"
                  onClick={() => analyzeMutation.mutate(files)}
                  disabled={analyzeMutation.isPending}
                >
                  {analyzeMutation.isPending ? (
                    <>
                      <Loader2 className="h-5 w-5 mr-2 animate-spin" />
                      Analyse en cours... (30-60 secondes)
                    </>
                  ) : (
                    <>
                      <ShieldCheck className="h-5 w-5 mr-2" />
                      Analyser {files.length} document{files.length > 1 ? 's' : ''}
                    </>
                  )}
                </Button>

                {analyzeMutation.isError && (
                  <div className="mt-3 p-3 bg-loss dark:bg-loss/20 border border-loss dark:border-loss rounded-lg">
                    <p className="text-sm text-loss dark:text-loss flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4 flex-shrink-0" />
                      {analyzeErrorMessage}
                    </p>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Results */}
      {currentAudit && (
        <>
          <div className="flex items-center justify-between gap-2">
            {linkedProjectName ? (
              <Badge variant="outline" className="flex items-center gap-1.5 px-3 py-1">
                <Link2 className="h-3.5 w-3.5" />
                Rattaché à {linkedProjectName}
              </Badge>
            ) : (
              <span />
            )}
            <Button variant="outline" onClick={() => setCurrentAudit(null)}>
              Nouvelle analyse
            </Button>
          </div>
          <AuditResults audit={currentAudit} />
          <DiversificationRadar audit={currentAudit} />
        </>
      )}

      {/* History */}
      {audits && audits.length > 0 && !currentAudit && (
        <Card elevation="raised">
          <CardHeader
            className="cursor-pointer"
            onClick={() => setShowHistory(!showHistory)}
          >
            <CardTitle className="flex items-center justify-between">
              <span>Historique des audits ({audits.length})</span>
              {showHistory ? (
                <ChevronUp className="h-5 w-5" />
              ) : (
                <ChevronDown className="h-5 w-5" />
              )}
            </CardTitle>
          </CardHeader>
          {showHistory && (
            <CardContent className="space-y-2">
              {audits.map((a) => (
                <div
                  key={a.id}
                  className="flex items-center justify-between border-b last:border-0 pb-2 last:pb-0 cursor-pointer hover:bg-muted/50 rounded p-2 -mx-2"
                  onClick={() => setCurrentAudit(a)}
                >
                  <div>
                    <p className="font-medium text-sm">{a.project_name || a.file_names[0]}</p>
                    <p className="text-xs text-muted-foreground">
                      {new Date(a.created_at).toLocaleDateString('fr-FR')}
                      {a.operator && ` — ${a.operator}`}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {a.risk_score != null && (
                      <Badge variant="outline">{a.risk_score}/10</Badge>
                    )}
                    <VerdictBadge verdict={a.verdict} />
                  </div>
                </div>
              ))}
            </CardContent>
          )}
        </Card>
      )}
    </div>
  )
}
