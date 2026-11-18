import { useRef, useState, type ChangeEvent } from 'react'
import { Download, FileText, HelpCircle, Loader2, Upload, Wallet } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { usePortfolioList } from '@/features/portfolio/hooks'
import { useToast } from '@/hooks/use-toast'
import { saveFile } from '../format'
import { useCsvPlatforms, useImportCsv } from '../hooks'
import { importErrorMessage, importFeedback } from '../importFeedback'
import type { CsvImportResult } from '../types'
import ImportResultPanel from './ImportResultPanel'
import PlatformSelect from './PlatformSelect'

interface ImportCSVFormProps {
  onSuccess?: () => void
  portfolioId?: string
  open?: boolean
  onOpenChange?: (open: boolean) => void
}

const TEMPLATE =
  'symbol;type;quantity;price;fee;date;notes\nBTC;buy;0.5;45000;10;2024-01-15;Premier achat\nETH;buy;2;2500;5;2024-01-16;DCA mensuel'

export default function ImportCSVForm({ onSuccess, portfolioId: initialPortfolioId, open, onOpenChange }: ImportCSVFormProps) {
  const { toast } = useToast()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<CsvImportResult | null>(null)
  const [portfolioId, setPortfolioId] = useState(initialPortfolioId || '')
  const [platform, setPlatform] = useState('auto')
  const [destination, setDestination] = useState('')
  const { data: portfolios } = usePortfolioList()
  const { data: platformsData } = useCsvPlatforms()

  const importer = useImportCsv(
    (imported) => {
      setResult(imported)
      const { succeeded, ...feedback } = importFeedback(imported)
      toast(feedback)
      if (succeeded) onSuccess?.()
    },
    (error) => toast({ variant: 'destructive', title: "Erreur d'import", description: importErrorMessage(error) })
  )

  const pickFile = (e: ChangeEvent<HTMLInputElement>) => {
    const picked = e.target.files?.[0]
    if (picked) {
      setFile(picked)
      setResult(null)
    }
  }

  const submit = () => {
    if (file && portfolioId) {
      importer.mutate({
        file,
        portfolioId: portfolioId || undefined,
        platform: platform !== 'auto' ? platform : undefined,
        destinationExchange: destination || undefined,
      })
    }
  }

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      setFile(null)
      setResult(null)
      setPlatform('auto')
      setDestination('')
    }
    onOpenChange?.(next)
  }

  const selectedPortfolio = portfolios?.find((p) => p.id === portfolioId)

  const formContent = (
    <div className="space-y-4 py-4">
      <div className="space-y-2">
        <label className="text-sm font-medium">Portefeuille de destination</label>
        <Select value={portfolioId} onValueChange={setPortfolioId}>
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
        {!portfolioId && <p className="text-sm text-destructive">Veuillez sélectionner un portefeuille</p>}
      </div>
      <div className="space-y-2">
        <label className="text-sm font-medium">Plateforme source</label>
        <Select value={platform} onValueChange={setPlatform}>
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
            {(platformsData?.platforms ?? []).map((name) => (
              <SelectItem key={name} value={name}>
                {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">Le format sera détecté automatiquement, ou sélectionnez manuellement.</p>
      </div>
      <div className="space-y-2">
        <label className="text-sm font-medium">Destination des transferts sortants</label>
        <PlatformSelect
          value={destination}
          onChange={setDestination}
          placeholder="Wallet froid par défaut (Tangem)"
          showTrustBadge={false}
        />
        <p className="text-xs text-muted-foreground">
          Chaque transfert sortant crée le transfert entrant correspondant sur cette plateforme, ou sur le wallet froid par
          défaut (Tangem) si aucune n'est choisie.
        </p>
      </div>
      <div className="rounded-lg bg-muted p-4 text-sm">
        <p className="font-medium mb-2">Plateformes supportées :</p>
        <ul className="list-disc list-inside space-y-1 text-muted-foreground">
          <li><strong>Crypto.com</strong> - Export depuis l'app (Paramètres → Exporter)</li>
          <li><strong>Binance</strong> - Historique des transactions</li>
          <li><strong>Kraken</strong> - Export des ledgers</li>
          <li><strong>Générique</strong> - Format InvestAI (symbol, type, quantity, price, date)</li>
        </ul>
        <p className="mt-3 text-muted-foreground">Les actifs sont créés automatiquement s'ils n'existent pas.</p>
        <Button
          variant="link"
          size="sm"
          className="mt-2 h-auto p-0"
          onClick={() => saveFile(new Blob([TEMPLATE], { type: 'text/csv;charset=utf-8;' }), 'template_transactions.csv')}
        >
          <Download className="h-3 w-3 mr-1" />
          Télécharger un modèle générique
        </Button>
      </div>
      <div className="space-y-2">
        <input ref={fileInputRef} type="file" accept=".csv" onChange={pickFile} className="hidden" />
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          aria-label="Sélectionner un fichier CSV à importer"
          className="w-full border-2 border-dashed rounded-lg p-8 text-center cursor-pointer hover:border-primary/50 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-primary transition-colors"
        >
          {file ? (
            <div className="flex items-center justify-center gap-2">
              <FileText className="h-6 w-6 text-primary" />
              <span className="font-medium">{file.name}</span>
            </div>
          ) : (
            <div className="space-y-2">
              <Upload className="h-8 w-8 mx-auto text-muted-foreground" />
              <p className="text-muted-foreground">Cliquez pour sélectionner un fichier CSV</p>
            </div>
          )}
        </button>
      </div>
      {result && <ImportResultPanel result={result} />}
      <div className="flex justify-end">
        <Button onClick={submit} disabled={!file || !portfolioId || importer.isPending}>
          {importer.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Importer dans {selectedPortfolio?.name || 'le portefeuille'}
        </Button>
      </div>
    </div>
  )

  if (open !== undefined && onOpenChange !== undefined) {
    return (
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Importer des transactions</DialogTitle>
            <DialogDescription>Importez vos transactions depuis un fichier CSV</DialogDescription>
          </DialogHeader>
          {formContent}
        </DialogContent>
      </Dialog>
    )
  }

  return formContent
}
