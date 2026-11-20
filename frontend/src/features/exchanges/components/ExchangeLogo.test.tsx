import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ExchangeLogo from './ExchangeLogo'

describe('ExchangeLogo', () => {
  it('affiche le logo d’une plateforme connue', () => {
    render(<ExchangeLogo exchange="binance" />)
    expect(screen.getByAltText('binance')).toBeInTheDocument()
  })

  it('affiche un logo pour chacune des plateformes déclarées', () => {
    for (const platform of ['binance', 'kraken', 'coinbase', 'bybit', 'okx']) {
      const { unmount } = render(<ExchangeLogo exchange={platform} />)
      expect(screen.getByAltText(platform)).toBeInTheDocument()
      unmount()
    }
  })

  it('reste affichable pour une plateforme totalement inconnue', () => {
    const { container } = render(<ExchangeLogo exchange="plateforme-inexistante" />)
    expect(container.firstChild).toBeInTheDocument()
    expect(screen.queryByAltText('plateforme-inexistante')).not.toBeInTheDocument()
  })

  it('respecte la taille demandée', () => {
    render(<ExchangeLogo exchange="binance" size={64} />)
    const img = screen.getByAltText('binance')
    expect(img).toHaveAttribute('width', '64')
    expect(img).toHaveAttribute('height', '64')
  })

  it('utilise 40 px par défaut', () => {
    render(<ExchangeLogo exchange="kraken" />)
    expect(screen.getByAltText('kraken')).toHaveAttribute('width', '40')
  })
})
