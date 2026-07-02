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
    // BTC/ETH appear both as column headers and as row headers.
    expect(screen.getAllByRole('columnheader').map((e) => e.textContent)).toEqual(
      expect.arrayContaining(['BTC', 'ETH']),
    )
    expect(screen.getAllByRole('rowheader').map((e) => e.textContent)).toEqual(
      expect.arrayContaining(['BTC', 'ETH']),
    )
  })

  it('gives each data cell a spoken label carrying the value + qualifier, so meaning survives without colour', () => {
    render(<CorrelationMatrix correlation={correlation} />)
    // Off-diagonal cell announces the pair, the numeric value and the qualitative label.
    expect(screen.getByLabelText(/BTC \/ ETH : 0\.72, Forte \+/)).toBeInTheDocument()
    // Diagonal cell is announced as such, not as a spurious correlation.
    expect(screen.getAllByLabelText(/diagonale/).length).toBeGreaterThanOrEqual(2)
  })
})
