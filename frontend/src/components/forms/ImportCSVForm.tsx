import { useState, useRef } from 'react'
import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { transactionsApi, portfoliosApi } from '@/services/api'
import { Upload, FileText, Loader2, CheckCircle, XCircle, Download, Wallet, HelpCircle } from 'lucide-react'
import { invalidateAllFinancialData } from '@/lib/invalidate-queries'

interface Portfolio {
  id: string
  name: string
}

interface ImportCSVFormProps {
  onSuccess?: () => void
  portfolioId?: string
  open?: boolean
  onOpenChange?: (open: boolean) => void
}

interface ImportResult {
  success_count: number
  error_count: number
  errors: string[]
  created_transactions: string[]
}

export default function ImportCSVForm({
  onSuccess,
  portfolioId: initialPortfolioId,
  open,
  onOpenChange,
}: ImportCSVFormProps) {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [importResult, setImportResult] = useState<ImportResult | null>(null)
  const [selectedPortfolioId, setSelectedPortfolioId] = useState<string>(initialPortfolioId || '')
  const [selectedPlatform, setSelectedPlatform] = useState<string>('auto')

  // Fetch portfolios for selection
  const { data: portfolios } = useQuery<Portfolio[]>({
    queryKey: ['portfolios'],
    queryFn: portfoliosApi.list,
  })

  // Fetch available platforms
  const { data: platformsData } = useQuery<{ platforms: string[] }>({
    queryKey: ['csv-platforms'],
    queryFn: transactionsApi.getCSVPlatforms,
  })

  const importMutation = useMutation({
    mutationFn: (file: File) => transactionsApi.importCSV(
      file,
      selectedPortfolioId || undefined,
      selectedPlatform !== 'auto' ? selectedPlatform : undefined
    ),
    onSuccess: (result: ImportResult) => {
      setImportResult(result)
      invalidateAllFinancialData(queryClient)

      if (result.success_count > 0 && result.error_count === 0) {
        toast({
          title: 'Import réussi',
          description: `${result.success_count} transactions importées avec succès.`,
        })
        onSuccess?.()
      } else if (result.success_count > 0 && result.error_count > 0) {
        toast({
          title: 'Import partiel',
          description: `${result.success_count} transactions importées, ${result.error_count} erreurs.`,
        })
      } else {
        toast({
          variant: 'destructive',
          title: 'Échec de l\'import',
          description: `${result.error_count} erreurs détectées.`,
        })
      }
    },
    onError: (error: unknown) => {
      const axiosError = error as import('axios').AxiosError<{ detail?: string }>
      toast({
        variant: 'destructive',
        title: 'Erreur',
        description: axiosError.response?.data?.detail || 'Impossible d\'importer le fichier.',
      })
    },
  })

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      setSelectedFile(file)
      setImportResult(null)
    }
  }

  const handleImport = () => {
    if (selectedFile && selectedPortfolioId) {
      importMutation.mutate(selectedFile)
    }
  }

  const downloadTemplate = () => {
    const template = 'symbol;type;quantity;price;fee;date;notes\nBTC;buy;0.5;45000;10;2024-01-15;Premier achat\nETH;buy;2;2500;5;2024-01-16;DCA mensuel'
    const blob = new Blob([template], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = 'template_transactions.csv'
    link.click()
  }

  const handleOpenChange = (newOpen: boolean) => {
    if (!newOpen) {
      // Reset state when closing
      setSelectedFile(null)
      setImportResult(null)
      setSelectedPlatform('auto')
    }
    onOpenChange?.(newOpen)
  }

  const platforms = platformsData?.platforms || []

  const selectedPortfolio = portfolios?.find(p => p.id === selectedPortfolioId)

  const formContent = (
    <div className="space-y-4 py-4">
      {/* Portfolio selector */}
      <div className="space-y-2">
        <label className="text-sm font-medium">Portefeuille de destination</label>
        <Select value={selectedPortfolioId} onValueChange={setSelectedPortfolioId}>
          <SelectTrigger>
            <SelectValue placeholder="Sélectionnez un portefeuille" />
          </SelectTrigger>
          <SelectContent>
            {portfolios?.map((portfolio) => (
              <SelectItem key={portfolio.id} value={portfolio.id}>
                <div className="flex items-center gap-2">
                  <Wallet className="h-4 w-4" />
                  {portfolio.name}
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {!selectedPortfolioId && (
          <p className="text-sm text-destructive">Veuillez sélectionner un portefeuille</p>
        )}
      </div>

      {/* Platform selector */}
      <div className="space-y-2">
        <label className="text-sm font-medium">Plateforme source</label>
        <Select value={selectedPlatform} onValueChange={setSelectedPlatform}>
          <SelectTrigger>
            <SelectValue placeholder="Sélectionnez la plateforme" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="auto">
              <div className="flex items-center gap-2">
                <HelpCircle className="h-4 w-4" />
                Auto-détection
              </div>
            </SelectItem>
            {platforms.map((platform) => (
              <SelectItem key={platform} value={platform}>
                {platform}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">
          Le format sera détecté automatiquement, ou sélectionnez manuellement.
        </p>
      </div>

      {/* Format info */}
      <div className="rounded-lg bg-muted p-4 text-sm">
        <p className="font-medium mb-2">Plateformes supportées :</p>
        <ul className="list-disc list-inside space-y-1 text-muted-foreground">
          <li><strong>Crypto.com</strong> - Export depuis l'app (Paramètres → Exporter)</li>
          <li><strong>Binance</strong> - Historique des transactions</li>
          <li><strong>Kraken</strong> - Export des ledgers</li>
          <li><strong>Générique</strong> - Format InvestAI (symbol, type, quantity, price, date)</li>
        </ul>
        <p className="mt-3 text-muted-foreground">
          Les actifs sont créés automatiquement s'ils n'existent pas.
        </p>
        <Button
          variant="link"
          size="sm"
          className="mt-2 h-auto p-0"
          onClick={downloadTemplate}
        >
          <Download className="h-3 w-3 mr-1" />
          Télécharger un modèle générique
        </Button>
      </div>

      {/* File input */}
      <div className="space-y-2">
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv"
          onChange={handleFileSelect}
          className="hidden"
        />
        <div
          onClick={() => fileInputRef.current?.click()}
          className="border-2 border-dashed rounded-lg p-8 text-center cursor-pointer hover:border-primary/50 transition-colors"
        >
          {selectedFile ? (
            <div className="flex items-center justify-center gap-2">
              <FileText className="h-6 w-6 text-primary" />
              <span className="font-medium">{selectedFile.name}</span>
            </div>
          ) : (
            <div className="space-y-2">
              <Upload className="h-8 w-8 mx-auto text-muted-foreground" />
              <p className="text-muted-foreground">
                Cliquez pour sélectionner un fichier CSV
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Import result */}
      {importResult && (
        <div className="rounded-lg border p-4 space-y-3">
          <div className="flex items-center gap-4">
            {importResult.success_count > 0 && (
              <div className="flex items-center gap-2 text-green-500">
                <CheckCircle className="h-5 w-5" />
                <span>{importResult.success_count} importées</span>
              </div>
            )}
            {importResult.error_count > 0 && (
              <div className="flex items-center gap-2 text-red-500">
                <XCircle className="h-5 w-5" />
                <span>{importResult.error_count} erreurs</span>
              </div>
            )}
          </div>

          {importResult.errors.length > 0 && (
            <div className="space-y-1">
              <p className="text-sm font-medium text-muted-foreground">Erreurs :</p>
              <div className="max-h-32 overflow-y-auto text-xs space-y-1">
                {importResult.errors.map((error, index) => (
                  <p key={index} className="text-red-500">
                    {error}
                  </p>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="flex justify-end">
        <Button
          onClick={handleImport}
          disabled={!selectedFile || !selectedPortfolioId || importMutation.isPending}
        >
          {importMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Importer dans {selectedPortfolio?.name || 'le portefeuille'}
        </Button>
      </div>
    </div>
  )

  // If open/onOpenChange props are provided, wrap in Dialog
  if (open !== undefined && onOpenChange !== undefined) {
    return (
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Importer des transactions</DialogTitle>
            <DialogDescription>
              Importez vos transactions depuis un fichier CSV
            </DialogDescription>
          </DialogHeader>
          {formContent}
        </DialogContent>
      </Dialog>
    )
  }

  // Otherwise, render form directly (for use inside existing Dialog)
  return formContent
}
