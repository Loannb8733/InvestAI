import { Component, type ReactNode, type ErrorInfo, useState, useCallback } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import NavRail from './NavRail'
import Header from './Header'
import { Button } from '@/components/ui/button'
import { AlertTriangle, RefreshCw } from 'lucide-react'

class RouteErrorBoundary extends Component<
  { children: ReactNode; resetKey: string },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: { children: ReactNode; resetKey: string }) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    if (import.meta.env.DEV) {
      console.error('Route error:', error, errorInfo)
    }
  }

  componentDidUpdate(prevProps: { resetKey: string }) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false, error: null })
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center min-h-[400px] p-8 text-center">
          <AlertTriangle className="h-16 w-16 text-destructive mb-4" />
          <h2 className="text-2xl font-serif font-medium mb-2">Une erreur est survenue</h2>
          <p className="text-muted-foreground mb-6 max-w-md">
            {this.state.error?.message || "Quelque chose s'est mal passé."}
          </p>
          <Button onClick={() => this.setState({ hasError: false, error: null })}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Réessayer
          </Button>
        </div>
      )
    }
    return this.props.children
  }
}

export default function Layout() {
  const location = useLocation()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const handleCloseSidebar = useCallback(() => {
    setSidebarOpen(false)
  }, [])

  const handleToggleSidebar = useCallback(() => {
    setSidebarOpen((prev) => !prev)
  }, [])

  return (
    <div className="flex h-screen bg-background">
      {/* WCAG 2.4.1 — let keyboard / screen-reader users bypass the nav rail
          and header, which take ~15 tab stops before the actual content. */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground focus:shadow-lg focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
      >
        Aller au contenu principal
      </a>
      <NavRail isOpen={sidebarOpen} onClose={handleCloseSidebar} />
      <div className="flex flex-col flex-1 overflow-hidden">
        <Header onMenuClick={handleToggleSidebar} />
        <main id="main-content" tabIndex={-1} className="flex-1 overflow-y-auto p-6">
          <RouteErrorBoundary resetKey={location.pathname}>
            <Outlet />
          </RouteErrorBoundary>
        </main>
      </div>
    </div>
  )
}
