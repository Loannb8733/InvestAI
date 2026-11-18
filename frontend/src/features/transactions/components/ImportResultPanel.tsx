import { CheckCircle, SkipForward, XCircle } from 'lucide-react'
import type { CsvImportResult } from '../types'

export default function ImportResultPanel({ result }: { result: CsvImportResult }) {
  const skipped = result.skipped_count ?? 0
  return (
    <div className="rounded-lg border p-4 space-y-3">
      <div className="flex items-center gap-4">
        {result.success_count > 0 && (
          <div className="flex items-center gap-2 text-gain">
            <CheckCircle className="h-5 w-5" />
            <span>{result.success_count} importées</span>
          </div>
        )}
        {result.error_count > 0 && (
          <div className="flex items-center gap-2 text-loss">
            <XCircle className="h-5 w-5" />
            <span>{result.error_count} erreurs</span>
          </div>
        )}
        {skipped > 0 && (
          <div className="flex items-center gap-2 text-muted-foreground">
            <SkipForward className="h-5 w-5" />
            <span>{skipped} déjà présentes</span>
          </div>
        )}
      </div>
      {result.errors.length > 0 && (
        <div className="space-y-1">
          <p className="text-sm font-medium text-muted-foreground">Erreurs :</p>
          <div className="max-h-32 overflow-y-auto text-xs space-y-1">
            {result.errors.map((error, index) => (
              <p key={index} className="text-loss">
                {error}
              </p>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
