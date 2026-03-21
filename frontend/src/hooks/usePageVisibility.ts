import { useState, useEffect } from 'react'

/**
 * Returns `true` when the page is visible, `false` when the tab is hidden.
 * Use this to pause polling and WebSocket connections when the user isn't looking.
 */
export function usePageVisibility(): boolean {
  const [visible, setVisible] = useState(() => document.visibilityState === 'visible')

  useEffect(() => {
    const handler = () => setVisible(document.visibilityState === 'visible')
    document.addEventListener('visibilitychange', handler)
    return () => document.removeEventListener('visibilitychange', handler)
  }, [])

  return visible
}
