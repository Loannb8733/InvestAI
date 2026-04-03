import { lazy } from 'react'

/**
 * Wrapper around React.lazy that auto-reloads the page once when a dynamic
 * import fails. This handles the common post-deploy scenario where chunk
 * filenames change but the client still has stale references cached.
 */
export function lazyWithRetry<T extends React.ComponentType<any>>(
  factory: () => Promise<{ default: T }>
) {
  return lazy(() =>
    factory().catch((err: unknown) => {
      const key = 'chunk_reload'
      if (!sessionStorage.getItem(key)) {
        sessionStorage.setItem(key, '1')
        window.location.reload()
        // Return a never-resolving promise so React doesn't render the error
        return new Promise(() => {})
      }
      sessionStorage.removeItem(key)
      throw err
    })
  )
}
