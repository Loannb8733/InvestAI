import { useState } from 'react'
import { Coins } from 'lucide-react'

interface CryptoIconProps {
  symbol: string
  size?: number
  className?: string
}

// Use CoinGecko's CDN for crypto icons
// Falls back to a generic icon if not found
export function CryptoIcon({ symbol, size = 24, className = '' }: CryptoIconProps) {
  const [hasError, setHasError] = useState(false)

  // Normalize symbol for the CDN (lowercase)
  const normalizedSymbol = symbol.toLowerCase()

  // Map common symbols to their CoinGecko IDs
  const symbolToId: Record<string, string> = {
    btc: 'bitcoin',
    eth: 'ethereum',
    usdt: 'tether',
    usdc: 'usd-coin',
    bnb: 'binancecoin',
    xrp: 'ripple',
    ada: 'cardano',
    doge: 'dogecoin',
    sol: 'solana',
    dot: 'polkadot',
    matic: 'matic-network',
    shib: 'shiba-inu',
    ltc: 'litecoin',
    avax: 'avalanche-2',
    link: 'chainlink',
    atom: 'cosmos',
    uni: 'uniswap',
    xlm: 'stellar',
    etc: 'ethereum-classic',
    xmr: 'monero',
    algo: 'algorand',
    vet: 'vechain',
    fil: 'filecoin',
    icp: 'internet-computer',
    aave: 'aave',
    cro: 'crypto-com-chain',
    inj: 'injective-protocol',
    ape: 'apecoin',
    sand: 'the-sandbox',
    mana: 'decentraland',
    grt: 'the-graph',
    ftm: 'fantom',
    theta: 'theta-token',
    axs: 'axie-infinity',
    near: 'near',
    egld: 'elrond-erd-2',
    flow: 'flow',
    xtz: 'tezos',
    eos: 'eos',
    mkr: 'maker',
    snx: 'havven',
    crv: 'curve-dao-token',
    ldo: 'lido-dao',
    rune: 'thorchain',
    kava: 'kava',
    zil: 'zilliqa',
    enj: 'enjincoin',
    bat: 'basic-attention-token',
    comp: 'compound-governance-token',
    yfi: 'yearn-finance',
    sushi: 'sushi',
    '1inch': '1inch',
    lrc: 'loopring',
    ren: 'republic-protocol',
    zrx: '0x',
    chz: 'chiliz',
    hot: 'holotoken',
    ankr: 'ankr',
    qtum: 'qtum',
    ont: 'ontology',
    omg: 'omisego',
    waves: 'waves',
    icx: 'icon',
    sc: 'siacoin',
    zen: 'zencash',
    dgb: 'digibyte',
    rvn: 'ravencoin',
    dcr: 'decred',
    nano: 'nano',
    hbar: 'hedera-hashgraph',
    ar: 'arweave',
    rose: 'oasis-network',
    one: 'harmony',
    glm: 'golem',
    stx: 'blockstack',
    ksm: 'kusama',
    audio: 'audius',
    celr: 'celer-network',
    ctsi: 'cartesi',
    skl: 'skale',
    band: 'band-protocol',
    ocean: 'ocean-protocol',
    storj: 'storj',
    bal: 'balancer',
    perp: 'perpetual-protocol',
    uma: 'uma',
    rlc: 'iexec-rlc',
    nkn: 'nkn',
    oxt: 'orchid-protocol',
    cvc: 'civic',
    nu: 'nucypher',
    trb: 'tellor',
    req: 'request-network',
    poly: 'polymath',
    rsr: 'reserve-rights-token',
    fet: 'fetch-ai',
    iotx: 'iotex',
    ogn: 'origin-protocol',
    nmr: 'numeraire',
    lpt: 'livepeer',
    knc: 'kyber-network-crystal',
    dnt: 'district0x',
    bnt: 'bancor',
    keep: 'keep-network',
    mln: 'melon',
    mir: 'mirror-protocol',
    srm: 'serum',
    ray: 'raydium',
    fida: 'bonfida',
    mngo: 'mango-markets',
    cope: 'cope',
    step: 'step-finance',
    orca: 'orca',
    sbr: 'saber',
    port: 'port-finance',
    tulip: 'tulip-protocol',
    sunny: 'sunny-aggregator',
  }

  const coinId = symbolToId[normalizedSymbol] || normalizedSymbol

  if (hasError) {
    return (
      <div
        className={`flex items-center justify-center rounded-full bg-muted ${className}`}
        style={{ width: size, height: size }}
      >
        <Coins className="h-3/5 w-3/5 text-muted-foreground" />
      </div>
    )
  }

  return (
    <img
      src={`https://assets.coingecko.com/coins/images/1/small/${coinId}.png`}
      alt={symbol}
      width={size}
      height={size}
      className={`rounded-full ${className}`}
      onError={() => {
        // Try alternative URL format
        const img = document.createElement('img')
        img.src = `https://cryptoicons.org/api/icon/${normalizedSymbol}/200`
        img.onload = () => {
          // Alternative worked, but we can't update state here easily
          // So just fall back to placeholder
        }
        img.onerror = () => setHasError(true)
        setHasError(true)
      }}
    />
  )
}

// Simple icon using cryptoicons.org API (more reliable for common coins)
export function CryptoIconSimple({ symbol, size = 24, className = '' }: CryptoIconProps) {
  const [hasError, setHasError] = useState(false)
  const normalizedSymbol = symbol.toLowerCase()

  if (hasError) {
    return (
      <div
        className={`flex items-center justify-center rounded-full bg-primary/20 ${className}`}
        style={{ width: size, height: size }}
      >
        <span className="text-xs font-bold text-primary">
          {symbol.slice(0, 2).toUpperCase()}
        </span>
      </div>
    )
  }

  return (
    <img
      src={`https://assets.coincap.io/assets/icons/${normalizedSymbol}@2x.png`}
      alt={symbol}
      width={size}
      height={size}
      className={`rounded-full ${className}`}
      onError={() => setHasError(true)}
    />
  )
}
