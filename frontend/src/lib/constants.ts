/**
 * Shared display constants for InvestAI.
 * Keep in sync with backend thresholds where applicable.
 */

/** Minimum value (in portfolio currency) below which an asset is considered "dust" */
export const MIN_DISPLAY_VALUE = 0.10

/** Crypto asset class classification for allocation grouping */
export const CRYPTO_ASSET_CLASSES: Record<string, string> = {
  // Layer 1
  BTC: 'L1', ETH: 'L1', SOL: 'L1', ADA: 'L1', AVAX: 'L1', DOT: 'L1',
  ATOM: 'L1', NEAR: 'L1', SUI: 'L1', APT: 'L1', ALGO: 'L1', XTZ: 'L1',
  EGLD: 'L1', FTM: 'L1', HBAR: 'L1', ICP: 'L1', TON: 'L1', SEI: 'L1',
  KAS: 'L1', TIA: 'L1', INJ: 'L1',
  // Layer 2
  MATIC: 'L2', ARB: 'L2', OP: 'L2', IMX: 'L2', MNT: 'L2', STRK: 'L2',
  ZK: 'L2', METIS: 'L2', POL: 'L2',
  // DeFi
  UNI: 'DeFi', AAVE: 'DeFi', MKR: 'DeFi', LDO: 'DeFi', SNX: 'DeFi',
  CRV: 'DeFi', COMP: 'DeFi', SUSHI: 'DeFi', CAKE: 'DeFi', PENDLE: 'DeFi',
  RUNE: 'DeFi', JUP: 'DeFi', RAY: 'DeFi', GMX: 'DeFi',
  // Stablecoins
  USDT: 'Stable', USDC: 'Stable', DAI: 'Stable', BUSD: 'Stable',
  FDUSD: 'Stable', TUSD: 'Stable', PYUSD: 'Stable', FRAX: 'Stable',
  LUSD: 'Stable', USDG: 'Stable', EURC: 'Stable', EURT: 'Stable',
  // Meme
  DOGE: 'Meme', SHIB: 'Meme', PEPE: 'Meme', FLOKI: 'Meme', WIF: 'Meme',
  BONK: 'Meme', MEME: 'Meme', TURBO: 'Meme', BRETT: 'Meme',
}

/** Labels for crypto asset classes */
export const CRYPTO_CLASS_LABELS: Record<string, string> = {
  L1: 'Layer 1',
  L2: 'Layer 2',
  DeFi: 'DeFi',
  Stable: 'Stablecoins',
  Meme: 'Meme',
  Other: 'Autres',
}

/** Colors for crypto asset classes */
export const CRYPTO_CLASS_COLORS: Record<string, string> = {
  L1: '#6366F1',     // indigo
  L2: '#818CF8',     // light indigo
  DeFi: '#10B981',   // emerald
  Stable: '#F59E0B', // amber
  Meme: '#F43F5E',   // rose
  Other: '#64748B',  // slate
}
