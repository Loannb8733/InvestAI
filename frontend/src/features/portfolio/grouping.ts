import type { PlatformShare, Position, PositionGroup, SoldAsset, SoldGroup } from './types'

export const UNASSIGNED = 'Non assigné'

export const platformOf = (exchange: string | null) => exchange || UNASSIGNED

export function platformShares(positions: Position[]): PlatformShare[] {
  const map = new Map<string, Omit<PlatformShare, 'platform' | 'roi'>>()
  for (const asset of positions) {
    const platform = platformOf(asset.exchange)
    const entry = map.get(platform) || { value: 0, totalInvested: 0, gainLoss: 0, assets: [] }
    entry.value += asset.current_value
    entry.totalInvested += asset.total_invested
    entry.gainLoss += asset.gain_loss
    entry.assets.push({ symbol: asset.symbol, value: asset.current_value })
    map.set(platform, entry)
  }
  return Array.from(map.entries())
    .map(([platform, data]) => ({
      platform,
      ...data,
      roi: data.totalInvested > 0 ? ((data.value - data.totalInvested) / data.totalInvested) * 100 : 0,
    }))
    .sort((a, b) => b.value - a.value)
}

const gainPercent = (value: number, invested: number) => (invested > 0 ? ((value - invested) / invested) * 100 : 0)

export function groupPositions(positions: Position[], platform: string | null): PositionGroup[] {
  const map = new Map<string, PositionGroup>()
  for (const asset of positions.filter((a) => !platform || platformOf(a.exchange) === platform)) {
    const existing = map.get(asset.symbol)
    if (existing) {
      existing.assets.push(asset)
      existing.totalQuantity += asset.quantity
      existing.totalValue += asset.current_value
      existing.totalInvested += asset.total_invested
      existing.totalGainLoss += asset.gain_loss
      existing.isMultiPlatform = true
      const totalQty = existing.assets.reduce((s, a) => s + a.quantity, 0)
      existing.avgBuyPrice = totalQty > 0 ? existing.totalInvested / totalQty : 0
      existing.totalGainLossPercent = gainPercent(existing.totalValue, existing.totalInvested)
    } else {
      map.set(asset.symbol, {
        symbol: asset.symbol,
        name: asset.name,
        asset_type: asset.asset_type,
        assets: [asset],
        totalQuantity: asset.quantity,
        totalValue: asset.current_value,
        totalInvested: asset.total_invested,
        totalGainLoss: asset.gain_loss,
        totalGainLossPercent: gainPercent(asset.current_value, asset.total_invested),
        currentPrice: asset.current_price,
        avgBuyPrice: asset.avg_buy_price,
        isMultiPlatform: false,
      })
    }
  }
  for (const group of map.values()) {
    const priced = group.assets.find((a) => a.current_price && a.current_price > 0)
    if (priced) group.currentPrice = priced.current_price
  }
  return Array.from(map.values()).sort((a, b) => b.totalValue - a.totalValue)
}

export const weightedBreakeven = (assets: Position[]) =>
  assets.reduce((s, a) => s + a.breakeven_price * a.quantity, 0) / assets.reduce((s, a) => s + a.quantity, 0)

export function soldPlatforms(soldAssets: SoldAsset[]) {
  const platforms = new Map<string, { value: number; count: number }>()
  for (const asset of soldAssets) {
    const platform = platformOf(asset.exchange)
    const entry = platforms.get(platform) || { value: 0, count: 0 }
    entry.value += asset.total_sold_value
    entry.count += 1
    platforms.set(platform, entry)
  }
  return Array.from(platforms.entries()).sort((a, b) => b[1].value - a[1].value)
}

const earlier = (a: string | null, b: string | null) => (a && (!b || new Date(a) < new Date(b)) ? a : b)
const later = (a: string | null, b: string | null) => (a && (!b || new Date(a) > new Date(b)) ? a : b)

export function groupSoldAssets(soldAssets: SoldAsset[]): SoldGroup[] {
  const groups = new Map<string, SoldGroup>()
  for (const asset of soldAssets) {
    const existing = groups.get(asset.symbol)
    if (existing) {
      existing.assets.push(asset)
      existing.totalBought += asset.total_bought
      existing.totalBoughtValue += asset.total_bought_value
      existing.totalSold += asset.total_sold
      existing.totalSoldValue += asset.total_sold_value
      existing.realizedGain += asset.realized_gain
      existing.firstTx = earlier(asset.first_transaction, existing.firstTx)
      existing.lastTx = later(asset.last_transaction, existing.lastTx)
    } else {
      groups.set(asset.symbol, {
        symbol: asset.symbol,
        name: asset.name,
        asset_type: asset.asset_type,
        assets: [asset],
        totalBought: asset.total_bought,
        totalBoughtValue: asset.total_bought_value,
        totalSold: asset.total_sold,
        totalSoldValue: asset.total_sold_value,
        realizedGain: asset.realized_gain,
        firstTx: asset.first_transaction,
        lastTx: asset.last_transaction,
      })
    }
  }
  return Array.from(groups.values()).sort((a, b) => b.totalBoughtValue - a.totalBoughtValue)
}
