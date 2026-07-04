import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Wallet } from 'lucide-react'
import StatCard from '@/components/ui/stat-card'

describe('StatCard', () => {
  it('rend le label et la valeur formatée (exposée en aria-live)', () => {
    render(
      <StatCard label="Patrimoine Total" icon={Wallet} value={12345.67} format={(n) => `${n.toFixed(2)} €`} />
    )
    expect(screen.getByRole('group', { name: 'Patrimoine Total' })).toBeInTheDocument()
    // La valeur formatée apparaît (span animé aria-hidden + span aria-live)
    expect(screen.getAllByText('12345.67 €').length).toBeGreaterThanOrEqual(1)
  })

  it('affiche un tiret accessible quand la valeur est absente', () => {
    render(<StatCard label="Capital Net" value={null} />)
    expect(screen.getByLabelText('Donnée indisponible')).toHaveTextContent('—')
  })

  it('masque la valeur et la variation en mode privé', () => {
    render(<StatCard label="Plus-value" value={5000} delta={4.2} privacy />)
    expect(screen.getByLabelText('Valeur masquée')).toHaveTextContent('••••••')
    expect(screen.queryByText(/4,2|4\.2/)).not.toBeInTheDocument()
  })

  it('verbalise la variation avec son contexte', () => {
    render(
      <StatCard
        label="Variation"
        value={100}
        delta={-2.5}
        deltaLabel="24h"
        formatDelta={(n) => `${n.toFixed(1)} %`}
      />
    )
    expect(screen.getByLabelText('-2.5 % sur 24h')).toBeInTheDocument()
  })

  it('affiche un squelette (aucune valeur) pendant le chargement', () => {
    const { container } = render(<StatCard label="Patrimoine" value={9999} loading />)
    expect(screen.queryByRole('group')).not.toBeInTheDocument()
    expect(container.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('expose le tooltip du label comme bouton accessible', () => {
    render(<StatCard label="Capital Net" tooltip="Définition du capital net" value={1} />)
    expect(screen.getByRole('button', { name: 'À propos de Capital Net' })).toBeInTheDocument()
  })
})
