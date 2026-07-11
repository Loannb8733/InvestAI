import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Receipt, Scissors, Coins, TrendingUp } from 'lucide-react'
import FeesSection from './optimizations/FeesSection'
import TaxLossSection from './optimizations/TaxLossSection'
import PassiveIncomeSection from './optimizations/PassiveIncomeSection'
import DcaBacktestSection from './optimizations/DcaBacktestSection'

type SubTab = 'fees' | 'harvest' | 'income' | 'dca'

/**
 * Onglet « Optimisations » de la page Rapports — le money-management :
 * frais, tax-loss harvesting, revenus passifs et backtest DCA.
 */
export default function OptimizationsTab() {
  const [subTab, setSubTab] = useState<SubTab>('fees')

  const subTabs: { id: SubTab; label: string; icon: React.ReactNode }[] = [
    { id: 'fees', label: 'Frais', icon: <Receipt className="h-4 w-4" /> },
    { id: 'harvest', label: 'Fiscalité TLH', icon: <Scissors className="h-4 w-4" /> },
    { id: 'income', label: 'Revenus passifs', icon: <Coins className="h-4 w-4" /> },
    { id: 'dca', label: 'Backtest DCA', icon: <TrendingUp className="h-4 w-4" /> },
  ]

  return (
    <div className="space-y-6">
      {/* Sub-tab bar */}
      <div className="flex gap-2 flex-wrap">
        {subTabs.map((t) => (
          <Button
            key={t.id}
            variant={subTab === t.id ? 'default' : 'outline'}
            size="sm"
            onClick={() => setSubTab(t.id)}
          >
            {t.icon}
            <span className="ml-1.5">{t.label}</span>
          </Button>
        ))}
      </div>

      {subTab === 'fees' && <FeesSection />}
      {subTab === 'harvest' && <TaxLossSection />}
      {subTab === 'income' && <PassiveIncomeSection />}
      {subTab === 'dca' && <DcaBacktestSection />}
    </div>
  )
}
