export const EXCHANGES = [
  'Binance',
  'Kraken',
  'Coinbase',
  'Crypto.com',
  'Bitstamp',
  'KuCoin',
  'Bybit',
  'OKX',
  'Gate.io',
  'Bitpanda',
  'Revolut',
  'Trade Republic',
] as const

export const COLD_WALLETS = [
  'Tangem',
  'Ledger',
  'Trezor',
  'SafePal',
  'Metamask',
] as const

export const CROWDFUNDING_PLATFORMS = [
  'Tokimo',
] as const

export const ALL_PLATFORMS = [...EXCHANGES, ...COLD_WALLETS, ...CROWDFUNDING_PLATFORMS] as const

// Trust scores: 1 (high risk) to 10 (self-custody)
export const PLATFORM_TRUST_SCORES: Record<string, number> = {
  // Self-custody (10)
  Tangem: 10,
  Ledger: 10,
  Trezor: 10,
  SafePal: 9,
  Metamask: 8,
  // Tier 1 CEX (7)
  Binance: 7,
  Kraken: 8,
  Coinbase: 7,
  'Crypto.com': 6,
  Bitstamp: 7,
  // Tier 2 CEX (5-6)
  KuCoin: 5,
  Bybit: 5,
  OKX: 6,
  'Gate.io': 5,
  Bitpanda: 6,
  // Neo-banks (6)
  Revolut: 6,
  'Trade Republic': 6,
  // Crowdfunding (4)
  Tokimo: 4,
}

export const DEFAULT_TRUST_SCORE = 4

export function getTrustScore(platform: string): number {
  return PLATFORM_TRUST_SCORES[platform] ?? DEFAULT_TRUST_SCORE
}

export function getTrustColor(score: number): string {
  if (score >= 8) return '#22c55e' // green
  if (score >= 5) return '#f59e0b' // amber
  return '#ef4444' // red
}

export function getTrustLabel(score: number): string {
  if (score >= 8) return 'Sécurisé'
  if (score >= 5) return 'Modéré'
  return 'Risqué'
}

export function isCrowdfundingPlatform(platform: string): boolean {
  return (CROWDFUNDING_PLATFORMS as readonly string[]).includes(platform)
}

export function isColdWallet(platform: string): boolean {
  return (COLD_WALLETS as readonly string[]).includes(platform)
}
