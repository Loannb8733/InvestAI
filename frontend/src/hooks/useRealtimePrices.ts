import { useState, useEffect, useRef, useCallback } from 'react'
import { useAuthStore } from '@/stores/authStore'

export interface PriceUpdate {
  symbol: string
  price: number
  change_24h_percent: number
  asset_type?: string
}

export function useRealtimePrices(symbols: string[]) {
  const [prices, setPrices] = useState<Record<string, PriceUpdate>>({})
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const token = useAuthStore((s) => s.accessToken)

  const connect = useCallback(() => {
    if (!token || symbols.length === 0) return

    // Clear any pending reconnect timer
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }

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
              asset_type: data.asset_type,
            },
          }))
        } else if (data.type === 'ping') {
          // Respond to server heartbeat
          ws.send(JSON.stringify({ action: 'pong' }))
        }
      } catch {
        // Ignore malformed WebSocket messages
      }
    }

    ws.onclose = () => {
      setConnected(false)
      // Reconnect after 5s
      reconnectTimerRef.current = setTimeout(connect, 5000)
    }

    ws.onerror = () => {
      ws.close()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, symbols.join(',')])

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      wsRef.current?.close()
    }
  }, [connect])

  return { prices, connected }
}
