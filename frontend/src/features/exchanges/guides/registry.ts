import { MAJOR_EXCHANGE_GUIDES } from './majorExchanges'
import { OTHER_EXCHANGE_GUIDES } from './otherExchanges'
import type { ExchangeGuideData } from './types'

const GUIDES = new Map([...MAJOR_EXCHANGE_GUIDES, ...OTHER_EXCHANGE_GUIDES].map((guide) => [guide.id, guide]))

export function guideFor(exchangeId: string): ExchangeGuideData | undefined {
  return GUIDES.get(exchangeId)
}
