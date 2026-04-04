import { lazy } from 'react'

/**
 * Wrapper around React.lazy that auto-reloads the page once when a dynamic
 * import fails. This handles the common post-deploy scenario where chunk
 * filenames change but the client still has stale references cached.
 *
 * Uses a per-module key so multiple stale chunks each get one reload attempt.
 */
export function lazyWithRetry<T extends React.ComponentType<any>>(
  factory: () => Promise<{ default: T }>
) {
  return lazy(() =>
    factory().catch((err: unknown) => {
      // Derive a stable key from the import path (in the error or factory string)
      const factoryStr = factory.toString()
      const pathMatch = factoryStr.match(/import\(["'](.+?)["']\)/) ||
                        factoryStr.match(/import\((.+?)\)/)
      const moduleKey = `chunk_reload_${pathMatch?.[1] ?? 'global'}`

      if (!sessionStorage.getItem(moduleKey)) {
        sessionStorage.setItem(moduleKey, '1')
        // Clear all stale chunk keys after 30s to allow future retries
        setTimeout(() => {
          Object.keys(sessionStorage)
            .filter((k) => k.startsWith('chunk_reload_'))
            .forEach((k) => sessionStorage.removeItem(k))
        }, 30000)
        window.location.reload()
        // Return a never-resolving promise so React doesn't flash the error boundary
        return new Promise<{ default: T }>(() => {})
      }
      sessionStorage.removeItem(moduleKey)
      throw err
    })
  )
}
