import { ArrowDownRight, ArrowLeftRight, ArrowUpRight, Coins, Gift, Lock, Percent, TrendingUp, Unlock, type LucideIcon } from 'lucide-react'
import type { TransactionType } from './types'

export interface TypeButton {
  value: TransactionType
  label: string
  shortLabel: string
  icon: LucideIcon
  color: string
  bg: string
  activeBg: string
  submitBg: string
}

const GAIN = { color: 'text-gain', bg: 'bg-gain/10 border-gain/20', activeBg: 'bg-gain/20 border-gain/40 ring-1 ring-gain/30', submitBg: 'bg-gain hover:bg-gain' }
const LOSS = { color: 'text-loss', bg: 'bg-loss/10 border-loss/20', activeBg: 'bg-loss/20 border-loss/40 ring-1 ring-loss/30', submitBg: 'bg-loss hover:bg-loss' }
const ACCENT = { color: 'text-accent', bg: 'bg-accent/10 border-accent/20', activeBg: 'bg-accent/20 border-accent/40 ring-1 ring-accent/30', submitBg: 'bg-accent hover:bg-accent' }
const WARNING = { color: 'text-warning', bg: 'bg-warning/10 border-warning/20', activeBg: 'bg-warning/20 border-warning/40 ring-1 ring-warning/30', submitBg: 'bg-warning hover:bg-warning' }

export const MOVEMENT_BUTTONS: TypeButton[] = [
  { value: 'buy', label: 'Achat', shortLabel: 'Achat', icon: ArrowDownRight, ...GAIN },
  { value: 'sell', label: 'Vente', shortLabel: 'Vente', icon: ArrowUpRight, ...LOSS },
  { value: 'transfer_in', label: 'Transfert entrant', shortLabel: 'Transfert In', icon: ArrowDownRight, ...ACCENT },
  { value: 'transfer_out', label: 'Transfert sortant', shortLabel: 'Transfert Out', icon: ArrowUpRight, ...WARNING },
  { value: 'staking_reward', label: 'Reward', shortLabel: 'Reward', icon: Coins, ...WARNING },
  { value: 'airdrop', label: 'Airdrop', shortLabel: 'Airdrop', icon: Gift, ...ACCENT },
  { value: 'conversion_in', label: 'Conversion entrante', shortLabel: 'Conv. In', icon: ArrowLeftRight, ...GAIN },
  { value: 'conversion_out', label: 'Conversion sortante', shortLabel: 'Conv. Out', icon: ArrowLeftRight, ...WARNING },
  { value: 'staking', label: 'Staking', shortLabel: 'Staking', icon: Lock, ...ACCENT },
  { value: 'unstaking', label: 'Unstaking', shortLabel: 'Unstaking', icon: Unlock, ...ACCENT },
]

export const ALL_TYPE_BUTTONS: TypeButton[] = [
  ...MOVEMENT_BUTTONS,
  { value: 'dividend', label: 'Dividende', shortLabel: 'Dividende', icon: TrendingUp, ...GAIN },
  { value: 'interest', label: 'Intérêt', shortLabel: 'Intérêt', icon: Percent, ...ACCENT },
]

export const findTypeButton = (buttons: TypeButton[], type: string) => buttons.find((b) => b.value === type)
