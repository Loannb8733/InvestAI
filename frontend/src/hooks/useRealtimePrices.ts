import { useState, useEffect, useRef, useCallback } from 'react'
import { useAuthStore } from '@/stores/authStore'

interface PriceUpdate {
  symbol: string
  price: number
  change_24h_percent: number
}

export function useRealtimePrices(symbols: string[]) {
  const [prices, setPrices] = useState<Record<string, PriceUpdate>>({})
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const token = useAuthStore((s) => s.accessToken)

  const connect = useCallback(() => {
    if (!token || symbols.length === 0) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const url = `${protocol}//${host}/api/v1/ws/prices?token=${token}`

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      ws.send(JSON.stringify({ action: 'subscribe', symbols }))
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'price') {
          setPrices((prev) => ({
            ...prev,
            [data.symbol]: {
              symbol: data.symbol,
              price: data.price,
              change_24h_percent: data.change_24h_percent,
            },
          }))
        }
      } catch {}
    }

    ws.onclose = () => {
      setConnected(false)
      // Reconnect after 5s
      setTimeout(connect, 5000)
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [token, symbols.join(',')])

  useEffect(() => {
    connect()
    return () => {
      wsRef.current?.close()
    }
  }, [connect])

  return { prices, connected }
}
