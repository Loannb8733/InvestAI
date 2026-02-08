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
import { useToast } from '@/hooks/use-toast'
import { reportsApi } from '@/services/api'
import {
  FileText,
  FileSpreadsheet,
  Receipt,
  TrendingUp,
  Calendar,
  Loader2,
  FileDown,
} from 'lucide-react'

export default function ReportsPage() {
  const { toast } = useToast()
  const [selectedYear, setSelectedYear] = useState<string>(
    new Date().getFullYear().toString()
  )
  const [loadingReport, setLoadingReport] = useState<string | null>(null)

  const { data: yearsData } = useQuery({
    queryKey: ['available-years'],
    queryFn: reportsApi.getAvailableYears,
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

  const reportCards = [
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
      id: 'tax',
      title: 'Déclaration Fiscale Crypto',
      description: 'Formulaire 2086 pour déclarer vos plus-values sur actifs numériques.',
      icon: Receipt,
      color: 'text-green-500',
      bgColor: 'bg-green-500/10',
      yearSelector: true,
      actions: [
        {
          label: 'PDF',
          icon: FileText,
          onClick: () =>
            handleDownload(
              'tax-pdf',
              () => reportsApi.downloadTaxPDF(parseInt(selectedYear)),
              `declaration_fiscale_crypto_${selectedYear}.pdf`
            ),
        },
        {
          label: 'Excel',
          icon: FileSpreadsheet,
          onClick: () =>
            handleDownload(
              'tax-excel',
              () => reportsApi.downloadTaxExcel(parseInt(selectedYear)),
              `declaration_fiscale_crypto_${selectedYear}.xlsx`
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
      ],
    },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Rapports</h1>
        <p className="text-muted-foreground">
          Générez et téléchargez vos rapports de performance et fiscaux
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {reportCards.map((report) => (
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
                    disabled={loadingReport === `${report.id}-${action.label.toLowerCase()}`}
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
        ))}
      </div>

      {/* Info section */}
      <Card className="bg-muted/50">
        <CardContent className="pt-6">
          <div className="flex items-start gap-4">
            <FileDown className="h-8 w-8 text-muted-foreground" />
            <div>
              <h3 className="font-semibold mb-2">À propos des rapports</h3>
              <ul className="text-sm text-muted-foreground space-y-1">
                <li>• Les rapports PDF sont optimisés pour l'impression et l'archivage</li>
                <li>• Les fichiers Excel permettent une analyse détaillée et personnalisée</li>
                <li>• La déclaration fiscale est fournie à titre indicatif - consultez un professionnel</li>
                <li>• Les données sont calculées en temps réel à partir de vos transactions</li>
              </ul>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
