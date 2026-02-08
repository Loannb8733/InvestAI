import { useCallback } from 'react'

/**
 * Hook to export a DOM element as PDF using the browser's print API.
 * No external dependency needed — uses window.print() with a print stylesheet.
 */
export function useExportPdf() {
  const exportToPdf = useCallback((title: string = 'InvestAI') => {
    // Set document title for PDF filename
    const originalTitle = document.title
    document.title = `${title} - ${new Date().toLocaleDateString('fr-FR')}`
    window.print()
    // Restore title after print dialog
    setTimeout(() => {
      document.title = originalTitle
    }, 1000)
  }, [])

  return { exportToPdf }
}
