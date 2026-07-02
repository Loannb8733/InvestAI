import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import DiversificationRadar from './DiversificationRadar'

// Nivo needs real layout measurement (absent in jsdom) — stub it out; the a11y
// contract under test lives in the sibling progressbars, not the SVG.
vi.mock('@nivo/radar', () => ({ ResponsiveRadar: () => null }))
vi.mock('@/components/charts/nivo-theme', () => ({
  useNivoTheme: () => ({ theme: {}, color: () => '#000' }),
}))

const audit = {
  diversification_impact: 'degrade',
  correlation_score: 0.72,
  portfolio_concentration: { geographic: 0.8, asset_type: 0.4, risk_return: 0.2 },
  suggested_investment: 1000,
} as unknown as Parameters<typeof DiversificationRadar>[0]['audit']

describe('DiversificationRadar — accessibility (not colour-only)', () => {
  it('exposes the coloured bars as progressbars with numeric values', () => {
    render(<DiversificationRadar audit={audit} />)
    const bars = screen.getAllByRole('progressbar')
    // 1 correlation-score bar + 3 concentration axes.
    expect(bars.length).toBe(4)
    const score = screen.getByLabelText(/Score de corrélation : 72%/)
    expect(score).toHaveAttribute('aria-valuenow', '72')
    expect(screen.getByLabelText(/Concentration Géographie : 80%/)).toBeInTheDocument()
  })

  it('distinguishes "dégrade" from "neutre" by icon, not colour alone', () => {
    const { container } = render(<DiversificationRadar audit={audit} />)
    // lucide renders the icon name as a data attribute; degrade must not reuse
    // the neutre triangle.
    expect(container.querySelector('.lucide-trending-down')).toBeTruthy()
  })
})
