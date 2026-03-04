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

export function isCrowdfundingPlatform(platform: string): boolean {
  return (CROWDFUNDING_PLATFORMS as readonly string[]).includes(platform)
}

export function isColdWallet(platform: string): boolean {
  return (COLD_WALLETS as readonly string[]).includes(platform)
}
