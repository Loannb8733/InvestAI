import type { ReactNode } from 'react'
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { pageNumbers } from '../ledger'
import { ITEMS_PER_PAGE, type Ledger } from '../useLedger'

function PageButton({ label, disabled, onClick, children }: { label: string; disabled: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <Button variant="outline" size="icon" className="h-8 w-8 tap-target" onClick={onClick} aria-label={label} disabled={disabled}>
      {children}
    </Button>
  )
}

export default function LedgerPagination({ ledger }: { ledger: Ledger }) {
  const { page, pageCount, setPage, sorted } = ledger
  const first = page === 1
  const last = page === pageCount
  return (
    <div className="flex items-center justify-between mt-4 pt-4 border-t">
      <div className="text-sm text-muted-foreground">
        {(page - 1) * ITEMS_PER_PAGE + 1}-{Math.min(page * ITEMS_PER_PAGE, sorted.length)} sur {sorted.length}
      </div>
      <div className="flex items-center gap-1">
        <PageButton label="Première page" disabled={first} onClick={() => setPage(1)}>
          <ChevronsLeft className="h-4 w-4" />
        </PageButton>
        <PageButton label="Page précédente" disabled={first} onClick={() => setPage((prev) => Math.max(1, prev - 1))}>
          <ChevronLeft className="h-4 w-4" />
        </PageButton>
        <div className="flex items-center gap-1 mx-2">
          {pageNumbers(page, pageCount).map((n) => (
            <Button
              key={n}
              variant={page === n ? 'default' : 'outline'}
              size="icon"
              className="h-8 w-8 tap-target"
              onClick={() => setPage(n)}
              aria-label={`Page ${n}`}
              aria-current={page === n ? 'page' : undefined}
            >
              {n}
            </Button>
          ))}
        </div>
        <PageButton label="Page suivante" disabled={last} onClick={() => setPage((prev) => Math.min(pageCount, prev + 1))}>
          <ChevronRight className="h-4 w-4" />
        </PageButton>
        <PageButton label="Dernière page" disabled={last} onClick={() => setPage(pageCount)}>
          <ChevronsRight className="h-4 w-4" />
        </PageButton>
      </div>
    </div>
  )
}
