import { useEffect } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { MotionConfig } from 'motion/react'
import { BrowserRouter } from 'react-router'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { ThemeProvider } from '@/components/theme-provider'
import { Toaster } from '@/components/ui/toaster'
import { queryClient } from '@/lib/queryClient'
import { useAuthStore } from '@/stores/authStore'
import AppRoutes from './AppRoutes'

export default function App() {
  const hydrateSession = useAuthStore((state) => state.hydrateSession)

  useEffect(() => {
    hydrateSession()
  }, [hydrateSession])

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <MotionConfig reducedMotion="user">
          <ThemeProvider defaultTheme="dark" storageKey="investai-theme-flux">
            <ErrorBoundary>
              <AppRoutes />
            </ErrorBoundary>
            <Toaster />
          </ThemeProvider>
        </MotionConfig>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
