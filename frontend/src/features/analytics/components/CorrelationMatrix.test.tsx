import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import CorrelationMatrix from './CorrelationMatrix'

const correlation = {
  symbols: ['BTC', 'ETH'],
  matrix: [
    [1, 0.72],
    [0.72, 1],
  ],
  strongly_correlated: [] as [string, string, number][],
  negatively_correlated: [] as [string, string, number][],
}

describe('CorrelationMatrix — accessibility (not colour-only)', () => {
  it('exposes proper table header semantics (row + column headers)', () => {
    render(<CorrelationMatrix correlation={correlation} />)
    expect(screen.getAllByRole('columnheader').map((e) => e.textContent)).toEqual(
      expect.arrayContaining(['BTC', 'ETH']),
    )
    expect(screen.getAllByRole('rowheader').map((e) => e.textContent)).toEqual(
      expect.arrayContaining(['BTC', 'ETH']),
    )
  })

  it('gives each data cell a spoken label carrying the value + qualifier, so meaning survives without colour', () => {
    render(<CorrelationMatrix correlation={correlation} />)
    expect(screen.getByLabelText(/BTC \/ ETH : 0\.72, Forte \+/)).toBeInTheDocument()
    expect(screen.getAllByLabelText(/diagonale/).length).toBeGreaterThanOrEqual(2)
  })
})
