export const TYPE_LABELS: Record<string, string> = {
  buy: 'Achat',
  sell: 'Vente',
  transfer_in: 'Transfert entrant',
  transfer_out: 'Transfert sortant',
  staking_reward: 'Reward',
  airdrop: 'Airdrop',
  conversion_in: 'Conversion entrante',
  conversion_out: 'Conversion sortante',
  dividend: 'Dividende',
  interest: 'Intérêts',
  fee: 'Frais',
  staking: 'Staking',
  unstaking: 'Unstaking',
}

export const TYPE_COLORS: Record<string, string> = {
  buy: 'text-gain',
  sell: 'text-loss',
  transfer_in: 'text-accent',
  transfer_out: 'text-warning',
  staking_reward: 'text-warning',
  airdrop: 'text-accent',
  conversion_in: 'text-gain',
  conversion_out: 'text-warning',
  dividend: 'text-gain',
  interest: 'text-accent',
  fee: 'text-loss',
  staking: 'text-accent',
  unstaking: 'text-accent',
}

export const TYPE_OPTIONS = [
  { value: 'all', label: 'Tous les types' },
  { value: 'buy', label: 'Achats' },
  { value: 'sell', label: 'Ventes' },
  { value: 'transfer_in', label: 'Transferts entrants' },
  { value: 'transfer_out', label: 'Transferts sortants' },
  { value: 'staking_reward', label: 'Rewards' },
  { value: 'airdrop', label: 'Airdrops' },
  { value: 'conversions', label: 'Conversions' },
  { value: 'dividend', label: 'Dividendes' },
  { value: 'interest', label: 'Intérêts' },
  { value: 'fee', label: 'Frais' },
  { value: 'staking', label: 'Staking' },
  { value: 'unstaking', label: 'Unstaking' },
]

export const DATE_OPTIONS = [
  { value: '0', label: 'Toutes les dates' },
  { value: '7', label: '7 derniers jours' },
  { value: '30', label: '30 derniers jours' },
  { value: '90', label: '90 derniers jours' },
  { value: 'ytd', label: 'Cette année' },
]

export const CONVERSION_TYPES = ['conversion_out', 'conversion_in']
export const INBOUND_TYPES = ['buy', 'transfer_in', 'staking_reward', 'airdrop', 'unstaking']
export const EXCLUDED_FROM_FLOWS = ['transfer_in', 'transfer_out', 'staking_reward', 'airdrop', 'conversion_in', 'conversion_out']

export const typeLabel = (type: string) => TYPE_LABELS[type] || type
export const typeColor = (type: string) => TYPE_COLORS[type] || 'text-gray-500'

export function platformLabel(exchange: string | null) {
  return exchange || 'Manuel'
}
