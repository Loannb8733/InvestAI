import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useToast } from '@/hooks/use-toast'
import { reportsApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import {
  FileText,
  FileSpreadsheet,
  Receipt,
  TrendingUp,
  Calendar,
  Loader2,
  FileDown,
  Download,
  ArrowRightLeft,
  Bitcoin,
  BarChart3,
} from 'lucide-react'
import RebalancingTab from '@/components/reports/RebalancingTab'

interface ReportAction {
  label: string
  icon: React.ComponentType<{ className?: string }>
  onClick: () => void
}

interface ReportCard {
  id: string
  title: string
  description: string
  icon: React.ComponentType<{ className?: string }>
  color: string
  bgColor: string
  yearSelector?: boolean
  actions: ReportAction[]
}

export default function ReportsPage() {
  const { toast } = useToast()
  const [selectedYear, setSelectedYear] = useState<string>(
    new Date().getFullYear().toString()
  )
  const [loadingReport, setLoadingReport] = useState<string | null>(null)

  const { data: yearsData } = useQuery({
    queryKey: queryKeys.reports.availableYears,
    queryFn: reportsApi.getAvailableYears,
    staleTime: 10 * 60_000,
  })

  const years = yearsData?.years || [new Date().getFullYear()]

  const downloadFile = (blob: Blob, filename: string) => {
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)
  }

  const handleDownload = async (
    reportType: string,
    downloadFn: () => Promise<Blob>,
    filename: string
  ) => {
    setLoadingReport(reportType)
    try {
      const blob = await downloadFn()
      downloadFile(blob, filename)
      toast({ title: 'Rapport téléchargé avec succès' })
    } catch (error) {
      toast({
        title: 'Erreur lors du téléchargement',
        variant: 'destructive',
      })
    } finally {
      setLoadingReport(null)
    }
  }

  const generalCards: ReportCard[] = [
    {
      id: 'performance',
      title: 'Rapport de Performance',
      description: 'Vue complète de vos portefeuilles avec gains/pertes, allocation et métriques clés.',
      icon: TrendingUp,
      color: 'text-blue-500',
      bgColor: 'bg-blue-500/10',
      actions: [
        {
          label: 'PDF',
          icon: FileText,
          onClick: () =>
            handleDownload(
              'performance-pdf',
              reportsApi.downloadPerformancePDF,
              `rapport_performance_${new Date().toISOString().split('T')[0]}.pdf`
            ),
        },
        {
          label: 'Excel',
          icon: FileSpreadsheet,
          onClick: () =>
            handleDownload(
              'performance-excel',
              reportsApi.downloadPerformanceExcel,
              `rapport_performance_${new Date().toISOString().split('T')[0]}.xlsx`
            ),
        },
      ],
    },
    {
      id: 'transactions',
      title: 'Historique des Transactions',
      description: 'Export complet de toutes vos transactions pour archivage ou comptabilité.',
      icon: Calendar,
      color: 'text-purple-500',
      bgColor: 'bg-purple-500/10',
      actions: [
        {
          label: 'PDF',
          icon: FileText,
          onClick: () =>
            handleDownload(
              'transactions-pdf',
              () => reportsApi.downloadTransactionsPDF(),
              `rapport_transactions_${new Date().toISOString().split('T')[0]}.pdf`
            ),
        },
        {
          label: 'Excel',
          icon: FileSpreadsheet,
          onClick: () =>
            handleDownload(
              'transactions-excel',
              () => reportsApi.downloadTransactionsExcel(),
              `transactions_${new Date().toISOString().split('T')[0]}.xlsx`
            ),
        },
        {
          label: 'CSV',
          icon: Download,
          onClick: () =>
            handleDownload(
              'transactions-csv',
              () => reportsApi.downloadTransactionsCSV(),
              `transactions_${new Date().toISOString().split('T')[0]}.csv`
            ),
        },
      ],
    },
  ]

  const cryptoTaxCard: ReportCard = {
    id: 'tax-crypto',
    title: 'Actifs Numériques (2086)',
    description: 'Formulaire 2086 pour déclarer vos plus-values sur actifs numériques. Régime fiscal spécifique crypto.',
    icon: Bitcoin,
    color: 'text-orange-500',
    bgColor: 'bg-orange-500/10',
    yearSelector: true,
    actions: [
      {
        label: 'PDF',
        icon: FileText,
        onClick: () =>
          handleDownload(
            'tax-crypto-pdf',
            () => reportsApi.downloadTaxPDF(parseInt(selectedYear)),
            `declaration_2086_crypto_${selectedYear}.pdf`
          ),
      },
      {
        label: 'Excel',
        icon: FileSpreadsheet,
        onClick: () =>
          handleDownload(
            'tax-crypto-excel',
            () => reportsApi.downloadTaxExcel(parseInt(selectedYear)),
            `declaration_2086_crypto_${selectedYear}.xlsx`
          ),
      },
    ],
  }

  const stocksTaxCard: ReportCard = {
    id: 'tax-stocks',
    title: 'Valeurs Mobilières (Flat Tax)',
    description: 'Plus-values sur actions, ETF et obligations. Prélèvement forfaitaire unique (PFU) 30% ou barème progressif.',
    icon: BarChart3,
    color: 'text-indigo-500',
    bgColor: 'bg-indigo-500/10',
    yearSelector: true,
    actions: [
      {
        label: 'PDF',
        icon: FileText,
        onClick: () =>
          handleDownload(
            'tax-stocks-pdf',
            () => reportsApi.downloadStockTaxPDF(parseInt(selectedYear)),
            `declaration_valeurs_mobilieres_${selectedYear}.pdf`
          ),
      },
      {
        label: 'Excel',
        icon: FileSpreadsheet,
        onClick: () =>
          handleDownload(
            'tax-stocks-excel',
            () => reportsApi.downloadStockTaxExcel(parseInt(selectedYear)),
            `declaration_valeurs_mobilieres_${selectedYear}.xlsx`
          ),
      },
    ],
  }

  const renderReportCard = (report: ReportCard) => (
    <Card key={report.id} className="flex flex-col">
      <CardHeader>
        <div className="flex items-center gap-3">
          <div className={`p-3 rounded-lg ${report.bgColor}`}>
            <report.icon className={`h-6 w-6 ${report.color}`} />
          </div>
          <div>
            <CardTitle className="text-lg">{report.title}</CardTitle>
          </div>
        </div>
        <CardDescription className="mt-2">
          {report.description}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col justify-end">
        {report.yearSelector && (
          <div className="mb-4">
            <label className="text-sm font-medium mb-2 block">
              Année fiscale
            </label>
            <Select value={selectedYear} onValueChange={setSelectedYear}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {years.map((year: number) => (
                  <SelectItem key={year} value={year.toString()}>
                    {year}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        <div className="flex gap-2">
          {report.actions.map((action) => (
            <Button
              key={action.label}
              variant="outline"
              className="flex-1"
              onClick={action.onClick}
              disabled={loadingReport !== null}
            >
              {loadingReport === `${report.id}-${action.label.toLowerCase()}` ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <action.icon className="h-4 w-4 mr-2" />
              )}
              {action.label}
            </Button>
          ))}
        </div>
      </CardContent>
    </Card>
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Rapports</h1>
        <p className="text-muted-foreground">
          Générez et téléchargez vos rapports de performance et fiscaux
        </p>
      </div>

      <Tabs defaultValue="exports" className="space-y-6">
        <TabsList>
          <TabsTrigger value="exports" className="gap-2">
            <FileDown className="h-4 w-4" />
            Exports
          </TabsTrigger>
          <TabsTrigger value="fiscal" className="gap-2">
            <Receipt className="h-4 w-4" />
            Fiscalité
          </TabsTrigger>
          <TabsTrigger value="strategy" className="gap-2">
            <ArrowRightLeft className="h-4 w-4" />
            Stratégie
          </TabsTrigger>
        </TabsList>

        <TabsContent value="exports" className="space-y-6">
          <div className="grid gap-6 md:grid-cols-2">
            {generalCards.map(renderReportCard)}
          </div>

          <Card className="bg-muted/50">
            <CardContent className="pt-6">
              <div className="flex items-start gap-4">
                <FileDown className="h-8 w-8 text-muted-foreground" />
                <div>
                  <h3 className="font-semibold mb-2">À propos des rapports</h3>
                  <ul className="text-sm text-muted-foreground space-y-1">
                    <li>• Les rapports PDF sont optimisés pour l'impression et l'archivage</li>
                    <li>• Les fichiers Excel permettent une analyse détaillée et personnalisée</li>
                    <li>• Les données sont calculées en temps réel à partir de vos transactions</li>
                  </ul>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="fiscal" className="space-y-6">
          <div className="grid gap-6 md:grid-cols-2">
            {renderReportCard(cryptoTaxCard)}
            {renderReportCard(stocksTaxCard)}
          </div>

          <Card className="bg-muted/50">
            <CardContent className="pt-6">
              <div className="flex items-start gap-4">
                <Receipt className="h-8 w-8 text-muted-foreground" />
                <div>
                  <h3 className="font-semibold mb-2">Régimes fiscaux</h3>
                  <ul className="text-sm text-muted-foreground space-y-1">
                    <li>• <strong>Actifs numériques (2086)</strong> : plus-values sur crypto-actifs, régime spécifique avec abattement</li>
                    <li>• <strong>Valeurs mobilières (Flat Tax)</strong> : actions, ETF, obligations — PFU 30% ou option barème progressif</li>
                    <li>• Les déclarations sont fournies à titre indicatif — consultez un professionnel</li>
                    <li>• Les dividendes sont inclus dans le rapport valeurs mobilières</li>
                  </ul>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="strategy">
          <RebalancingTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
