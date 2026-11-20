import { Coins } from 'lucide-react'

const LOGO_URLS: Record<string, string> = {
  binance: '/logos/binance.png',
  kraken: '/logos/kraken.png',
  cryptocom: '/logos/cryptocom.svg',
  coinbase: '/logos/coinbase.svg',
  kucoin: '/logos/kucoin.svg',
  okx: '/logos/okx.svg',
  bybit: '/logos/bybit.svg',
  bitpanda: '/logos/bitpanda.svg',
  bitstamp: '/logos/bitstamp.svg',
  gateio: '/logos/gateio.svg',
}

const FALLBACK_COLORS: Record<string, string> = {
  binance: 'bg-[#F3BA2F]',
  kraken: 'bg-[oklch(var(--chart-2))]',
  coinbase: 'bg-[#0052FF]',
  cryptocom: 'bg-[#002D74]',
  kucoin: 'bg-[oklch(var(--chart-3))]',
  bybit: 'bg-[#F7A600]',
  okx: 'bg-[oklch(var(--foreground))]',
  bitpanda: 'bg-[oklch(var(--muted-foreground))]',
  bitstamp: 'bg-[oklch(var(--chart-3))]',
  gateio: 'bg-[oklch(var(--chart-5))]',
}

const FALLBACK_LABELS: Record<string, string> = {
  binance: 'BN',
  kraken: 'KR',
  coinbase: 'CB',
  cryptocom: 'CC',
  kucoin: 'KC',
  bybit: 'BY',
  okx: 'OK',
  bitpanda: 'BP',
  bitstamp: 'BS',
  gateio: 'GT',
}

export default function ExchangeLogo({ exchange, size = 40 }: { exchange: string; size?: number }) {
  if (LOGO_URLS[exchange]) {
    return (
      <img src={LOGO_URLS[exchange]} alt={exchange} width={size} height={size} className="shrink-0 rounded-lg" />
    )
  }

  return (
    <div
      className={`${FALLBACK_COLORS[exchange] || 'bg-muted-foreground'} text-white rounded-xl flex items-center justify-center font-bold shrink-0`}
      style={{ width: size, height: size, fontSize: size * 0.35 }}
    >
      {FALLBACK_LABELS[exchange] || <Coins style={{ width: size * 0.5, height: size * 0.5 }} />}
    </div>
  )
}
