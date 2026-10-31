import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import DashboardRiskCards from './DashboardRiskCards'

const riskMetrics = {
  volatility: 20,
  sharpe_ratio: 1.5 as number | null,
  max_drawdown: { max_drawdown_percent: 10 },
  var_95: { var_percent: 2, var_amount: 100, confidence_level: 95 },
}

describe('DashboardRiskCards', () => {
  it('affiche le Sharpe quand la période le permet', () => {
    render(<DashboardRiskCards riskMetrics={riskMetrics} />)
    expect(screen.getByText('1.50')).toBeInTheDocument()
    expect(screen.getByText('Bon')).toBeInTheDocument()
  })

  it("n'affiche aucun Sharpe sous trois mois", () => {
    render(<DashboardRiskCards riskMetrics={{ ...riskMetrics, sharpe_ratio: null }} />)
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.getByText('3 mois minimum')).toBeInTheDocument()
  })
})
