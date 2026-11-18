import type { AxiosError } from 'axios'
import type { CsvImportResult } from './types'

interface Feedback {
  title: string
  description: string
  variant?: 'destructive'
  succeeded: boolean
}

export function importFeedback(result: CsvImportResult): Feedback {
  const skipped = result.skipped_count ?? 0
  const skippedNote = skipped > 0 ? ` ${skipped} déjà présentes, ignorées.` : ''
  if (result.success_count > 0 && result.error_count === 0) {
    return {
      title: 'Import réussi',
      description: `${result.success_count} transactions importées avec succès.${skippedNote}`,
      succeeded: true,
    }
  }
  if (result.success_count > 0 && result.error_count > 0) {
    return {
      title: 'Import partiel',
      description: `${result.success_count} transactions importées, ${result.error_count} erreurs.${skippedNote}`,
      succeeded: false,
    }
  }
  if (result.error_count === 0 && skipped > 0) {
    return { title: 'Rien de nouveau', description: `${skipped} transactions étaient déjà présentes.`, succeeded: false }
  }
  return { variant: 'destructive', title: "Échec de l'import", description: `${result.error_count} erreurs détectées.`, succeeded: false }
}

export function importErrorMessage(error: unknown): string {
  const response = (error as AxiosError<{ detail?: string | object } | string>).response
  const data = response?.data
  let message = "Impossible d'importer le fichier."
  if (data) {
    if (typeof data === 'string') message = data
    else if (typeof data.detail === 'string') message = data.detail
    else if (typeof data.detail === 'object') message = JSON.stringify(data.detail)
  }
  return response?.status ? `[${response.status}] ${message}` : message
}
