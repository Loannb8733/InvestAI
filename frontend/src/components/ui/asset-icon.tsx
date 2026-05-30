import { useState } from 'react'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'

interface AssetIconProps {
  symbol: string
  name?: string
  assetType?: string
  size?: number
  showTooltip?: boolean
  className?: string
}


// Asset type labels
const assetTypeLabels: Record<string, string> = {
  crypto: 'Crypto',
  stock: 'Action',
  etf: 'ETF',
  real_estate: 'Immobilier',
  bond: 'Obligation',
  fiat: 'Fiat',
  other: 'Autre',
}

// Custom icon URLs for symbols that don't match CoinCap naming
const customIconUrls: Record<string, string> = {
  om: 'https://assets.coingecko.com/coins/images/12151/small/OM_Token.png',
  kaito: 'https://coin-images.coingecko.com/coins/images/54411/small/Qm4DW488_400x400.jpg',
  pendle: 'https://coin-images.coingecko.com/coins/images/15069/small/Pendle_Logo_Normal-03.png',
  usdg: 'https://coin-images.coingecko.com/coins/images/51281/small/GDN_USDG_Token_200x200.png',
}

// Get the icon URL for a symbol
const getIconUrl = (symbol: string): string => {
  const normalizedSymbol = symbol.toLowerCase()
  if (customIconUrls[normalizedSymbol]) {
    return customIconUrls[normalizedSymbol]
  }
  return `https://assets.coincap.io/assets/icons/${normalizedSymbol}@2x.png`
}

export function AssetIcon({
  symbol,
  name,
  assetType = 'crypto',
  size = 40,
  showTooltip = true,
  className = '',
}: AssetIconProps) {
  const [imgError, setImgError] = useState(false)

  const renderIcon = () => {
    // For crypto, try to load the icon from CDN
    if (assetType === 'crypto' && !imgError) {
      return (
        <div
          className={`relative rounded-full overflow-hidden bg-transparent dark:bg-white ${className}`}
          style={{ width: size, height: size }}
        >
          <img
            src={getIconUrl(symbol)}
            alt={symbol}
            className="w-full h-full object-cover rounded-full"
            onError={() => setImgError(true)}
          />
        </div>
      )
    }

    // Fallback: show initials with gradient background
    return (
      <div
        className={`flex items-center justify-center rounded-full bg-secondary text-secondary-foreground font-bold ${className}`}
        style={{ width: size, height: size, fontSize: size * 0.35 }}
      >
        {symbol.slice(0, 2).toUpperCase()}
      </div>
    )
  }

  if (!showTooltip) {
    return renderIcon()
  }

  return (
    <TooltipProvider delayDuration={100}>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="cursor-pointer transition-transform hover:scale-110">
            {renderIcon()}
          </div>
        </TooltipTrigger>
        <TooltipContent
          side="top"
          className="bg-popover text-popover-foreground border border-border shadow-md px-3 py-2"
        >
          <div className="flex flex-col items-center gap-1">
            <span className="font-bold text-sm">{symbol}</span>
            {name && <span className="text-xs text-muted-foreground">{name}</span>}
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-muted">
              {assetTypeLabels[assetType] || assetType}
            </span>
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

// Compact version for tables - icon only with hover effect
export function AssetIconCompact({
  symbol,
  name,
  assetType = 'crypto',
  size = 32,
}: AssetIconProps) {
  const [imgError, setImgError] = useState(false)

  const renderIcon = () => {
    if (assetType === 'crypto' && !imgError) {
      return (
        <img
          src={getIconUrl(symbol)}
          alt={symbol}
          className="w-full h-full object-cover rounded-full"
          onError={() => setImgError(true)}
        />
      )
    }

    return (
      <div
        className={`flex items-center justify-center w-full h-full rounded-full bg-secondary text-secondary-foreground font-semibold`}
        style={{ fontSize: size * 0.4 }}
      >
        {symbol.slice(0, 2).toUpperCase()}
      </div>
    )
  }

  return (
    <TooltipProvider delayDuration={0}>
      <Tooltip>
        <TooltipTrigger asChild>
          <div
            className="rounded-full overflow-hidden cursor-pointer transition-all hover:scale-110 hover:ring-2 hover:ring-primary/50 bg-transparent dark:bg-white"
            style={{ width: size, height: size }}
          >
            {renderIcon()}
          </div>
        </TooltipTrigger>
        <TooltipContent
          side="right"
          align="center"
          className="bg-popover text-popover-foreground border border-border shadow-md px-4 py-3 rounded-lg"
        >
          <div className="flex items-center gap-3">
            <div
              className="flex items-center justify-center rounded-full overflow-hidden bg-transparent dark:bg-white"
              style={{ width: 40, height: 40 }}
            >
              {assetType === 'crypto' && !imgError ? (
                <img
                  src={getIconUrl(symbol)}
                  alt={symbol}
                  className="w-full h-full object-cover rounded-full"
                />
              ) : (
                <div className={`w-full h-full rounded-full flex items-center justify-center bg-secondary text-secondary-foreground font-bold text-sm`}>
                  {symbol.slice(0, 2).toUpperCase()}
                </div>
              )}
            </div>
            <div className="flex flex-col">
              <span className="font-bold text-base">{symbol}</span>
              {name && (
                <span className="text-sm text-muted-foreground max-w-[150px] truncate">
                  {name}
                </span>
              )}
              <span className="text-[10px] text-muted-foreground mt-0.5">
                {assetTypeLabels[assetType] || assetType}
              </span>
            </div>
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
