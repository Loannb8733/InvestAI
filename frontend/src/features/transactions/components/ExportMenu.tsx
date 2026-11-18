import { Download, FileSpreadsheet, Loader2, SlidersHorizontal } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import type { Exports } from '../useExports'

interface ExportMenuProps {
  exports: Exports
  filtered: boolean
  loadedCount: number
  selectedCount: number
}

export default function ExportMenu({ exports, filtered, loadedCount, selectedCount }: ExportMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline">
          <Download className="h-4 w-4 mr-2" />
          Exporter
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={exports.exportAll} disabled={exports.exportingAll}>
          {exports.exportingAll ? (
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          ) : (
            <FileSpreadsheet className="h-4 w-4 mr-2" />
          )}
          Tout exporter (serveur)
        </DropdownMenuItem>
        {filtered && (
          <DropdownMenuItem onClick={exports.exportFiltered}>
            <SlidersHorizontal className="h-4 w-4 mr-2" />
            Exporter filtrés ({loadedCount})
          </DropdownMenuItem>
        )}
        {selectedCount > 0 && (
          <DropdownMenuItem onClick={exports.exportSelected}>
            <Checkbox className="h-4 w-4 mr-2" checked />
            Exporter sélection ({selectedCount})
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
