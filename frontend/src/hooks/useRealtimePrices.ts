import { useState, useEffect, useRef, useCallback } from 'react'
import { useAuthStore } from '@/stores/authStore'
import { usePageVisibility } from '@/hooks/usePageVisibility'

export interface PriceUpdate {
  symbol: string
  price: number
  change_24h_percent: number
  asset_type?: string
}

const BASE_DELAY = 1_000   // 1s initial retry
const MAX_DELAY = 60_000   // 60s cap
const BACKOFF_FACTOR = 2

export function useRealtimePrices(symbols: string[]) {
  const [prices, setPrices] = useState<Record<string, PriceUpdate>>({})
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const retryDelayRef = useRef(BASE_DELAY)
  const token = useAuthStore((s) => s.accessToken)
  const pageVisible = usePageVisibility()

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
  }, [])

  const disconnect = useCallback(() => {
    clearReconnectTimer()
    if (wsRef.current) {
      wsRef.current.onclose = null // prevent auto-reconnect on intentional close
      wsRef.current.close()
      wsRef.current = null
    }
    setConnected(false)
  }, [clearReconnectTimer])

  const connect = useCallback(() => {
    if (!token || symbols.length === 0) return

    clearReconnectTimer()

    // Don't open a second socket
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return

    const apiUrl = import.meta.env.VITE_API_URL || '/api/v1'
    const wsBase = apiUrl.replace(/^http/, 'ws')
    const url = apiUrl.startsWith('http')
      ? `${wsBase}/ws/prices`
      : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}${apiUrl}/ws/prices`

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      retryDelayRef.current = BASE_DELAY // reset backoff on success
      ws.send(JSON.stringify({ action: 'auth', token }))
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)

        if (data.type === 'auth' && data.status === 'ok') {
          setConnected(true)
          ws.send(JSON.stringify({ action: 'subscribe', symbols }))
        } else if (data.type === 'price') {
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
          ws.send(JSON.stringify({ action: 'pong' }))
        }
      } catch {
        // Ignore malformed messages
      }
    }

    ws.onclose = () => {
      setConnected(false)
      wsRef.current = null
      // Exponential backoff: 1s → 2s → 4s → 8s → … → 60s max
      const delay = retryDelayRef.current
      retryDelayRef.current = Math.min(delay * BACKOFF_FACTOR, MAX_DELAY)
      reconnectTimerRef.current = setTimeout(connect, delay)
    }

    ws.onerror = () => {
      ws.close()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, symbols.join(','), clearReconnectTimer])

  // Pause WS when tab is hidden, reconnect when visible
  useEffect(() => {
    if (pageVisible) {
      retryDelayRef.current = BASE_DELAY
      connect()
    } else {
      disconnect()
    }
    return () => disconnect()
  }, [pageVisible, connect, disconnect])

  return { prices, connected }
}
