import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ExchangeLogo from '../exchange-logo'

/**
 * ARC-07 — premier morceau extrait d'ExchangesPage.tsx (1 368 lignes, aucun test).
 *
 * Ce composant est purement présentationnel : ni état, ni effet, ni requête. C'est
 * ce qui le rend extractible sans risque, contrairement au reste de la page qui
 * partage 28 hooks — y toucher sans couverture de test serait imprudent.
 */

describe('ExchangeLogo', () => {
  it('affiche le logo d’une plateforme connue', () => {
    render(<ExchangeLogo exchange="binance" />)
    expect(screen.getByAltText('binance')).toBeInTheDocument()
  })

  it('affiche un logo pour chacune des plateformes déclarées', () => {
    // Constat de l'extraction : toutes les plateformes listées dans FALLBACK_LABELS
    // figurent aussi dans LOGO_URLS. Le repli par initiales n'est donc JAMAIS atteint
    // pour une plateforme connue — et il ne le sera pas davantage si un fichier de
    // logo devient introuvable, faute de gestionnaire `onError` sur l'image.
    for (const plateforme of ['binance', 'kraken', 'coinbase', 'bybit', 'okx']) {
      const { unmount } = render(<ExchangeLogo exchange={plateforme} />)
      expect(screen.getByAltText(plateforme)).toBeInTheDocument()
      unmount()
    }
  })

  it('reste affichable pour une plateforme totalement inconnue', () => {
    const { container } = render(<ExchangeLogo exchange="plateforme-inexistante" />)
    // Ni logo, ni initiales : une icône générique, mais quelque chose est rendu.
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
