import { useCallback, useEffect, useState } from 'react'
import type { UseFormReturn } from 'react-hook-form'
import { toNum, type AddInput, type AddOutput } from './addSchema'

export function useTotalInput({ watch, setValue }: UseFormReturn<AddInput, unknown, AddOutput>) {
  const quantity = toNum(watch('quantity'))
  const price = toNum(watch('price'))
  const fee = toNum(watch('fee'))
  const total = quantity * price + fee
  const [input, setInput] = useState('')
  const [editing, setEditing] = useState(false)

  const edit = useCallback(
    (raw: string) => {
      setInput(raw)
      setEditing(true)
      const typed = parseFloat(raw)
      if (!isNaN(typed) && price > 0) setValue('quantity', parseFloat(Math.max(0, (typed - fee) / price).toFixed(8)))
    },
    [price, fee, setValue]
  )

  useEffect(() => {
    if (!editing) setInput(total > 0 ? total.toFixed(2) : '')
  }, [total, editing])

  const applyPrice = (market: number) => {
    setValue('price', parseFloat(market.toFixed(8)))
    setEditing(false)
  }

  const clear = () => {
    setInput('')
    setEditing(false)
  }

  return { quantity, total, input, edit, stop: () => setEditing(false), applyPrice, clear }
}

export type TotalInput = ReturnType<typeof useTotalInput>
