import { lazy, Suspense, useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { ThemeProvider } from '@/components/theme-provider'
import { Toaster } from '@/components/ui/toaster'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import Layout from '@/components/layout/Layout'
import { Loader2 } from 'lucide-react'

// Eagerly loaded (auth pages — needed immediately)
import LoginPage from '@/pages/LoginPage'
import RegisterPage from '@/pages/RegisterPage'
import ForgotPasswordPage from '@/pages/ForgotPasswordPage'
import ResetPasswordPage from '@/pages/ResetPasswordPage'
import VerifyEmailPage from '@/pages/VerifyEmailPage'
import NotFoundPage from '@/pages/NotFoundPage'

// Lazy loaded (behind auth, loaded on demand)
const DashboardPage = lazy(() => import('@/pages/DashboardPage'))
const PortfolioPage = lazy(() => import('@/pages/PortfolioPage'))
const TransactionsPage = lazy(() => import('@/pages/TransactionsPage'))
const ExchangesPage = lazy(() => import('@/pages/ExchangesPage'))
const AnalyticsPage = lazy(() => import('@/pages/AnalyticsPage'))
const AlertsPage = lazy(() => import('@/pages/AlertsPage'))
const PredictionsPage = lazy(() => import('@/pages/PredictionsPage'))
const ReportsPage = lazy(() => import('@/pages/ReportsPage'))
const SettingsPage = lazy(() => import('@/pages/SettingsPage'))
const AdminPage = lazy(() => import('@/pages/AdminPage'))
const NotesPage = lazy(() => import('@/pages/NotesPage'))
const CalendarPage = lazy(() => import('@/pages/CalendarPage'))
const SimulationsPage = lazy(() => import('@/pages/SimulationsPage'))
const InsightsPage = lazy(() => import('@/pages/InsightsPage'))
const GoalsPage = lazy(() => import('@/pages/GoalsPage'))
const SmartInsightsPage = lazy(() => import('@/pages/SmartInsightsPage'))

function PageLoader() {
  return (
    <div className="flex items-center justify-center h-[50vh]">
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
    </div>
  )
}

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)
  const isHydrating = useAuthStore((state) => state.isHydrating)

  if (isHydrating) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return isAuthenticated ? <>{children}</> : <Navigate to="/login" />
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, user } = useAuthStore()
  if (!isAuthenticated) return <Navigate to="/login" />
  if (user?.role !== 'admin') return <Navigate to="/" />
  return <>{children}</>
}

function App() {
  const hydrateSession = useAuthStore((state) => state.hydrateSession)

  useEffect(() => {
    hydrateSession()
  }, [hydrateSession])

  return (
    <ThemeProvider defaultTheme="dark" storageKey="investai-theme">
      <ErrorBoundary>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/verify-email" element={<VerifyEmailPage />} />
          <Route
            path="/"
            element={
              <PrivateRoute>
                <Layout />
              </PrivateRoute>
            }
          >
            <Route index element={<Suspense fallback={<PageLoader />}><DashboardPage /></Suspense>} />
            <Route path="portfolio" element={<Suspense fallback={<PageLoader />}><PortfolioPage /></Suspense>} />
            <Route path="transactions" element={<Suspense fallback={<PageLoader />}><TransactionsPage /></Suspense>} />
            <Route path="exchanges" element={<Suspense fallback={<PageLoader />}><ExchangesPage /></Suspense>} />
            <Route path="analytics" element={<Suspense fallback={<PageLoader />}><AnalyticsPage /></Suspense>} />
            <Route path="alerts" element={<Suspense fallback={<PageLoader />}><AlertsPage /></Suspense>} />
            <Route path="predictions" element={<Suspense fallback={<PageLoader />}><PredictionsPage /></Suspense>} />
            <Route path="reports" element={<Suspense fallback={<PageLoader />}><ReportsPage /></Suspense>} />
            <Route path="notes" element={<Suspense fallback={<PageLoader />}><NotesPage /></Suspense>} />
            <Route path="calendar" element={<Suspense fallback={<PageLoader />}><CalendarPage /></Suspense>} />
            <Route path="simulations" element={<Suspense fallback={<PageLoader />}><SimulationsPage /></Suspense>} />
            <Route path="insights" element={<Suspense fallback={<PageLoader />}><InsightsPage /></Suspense>} />
            <Route path="smart-insights" element={<Suspense fallback={<PageLoader />}><SmartInsightsPage /></Suspense>} />
            <Route path="goals" element={<Suspense fallback={<PageLoader />}><GoalsPage /></Suspense>} />
            <Route path="settings" element={<Suspense fallback={<PageLoader />}><SettingsPage /></Suspense>} />
            <Route
              path="admin"
              element={
                <AdminRoute>
                  <Suspense fallback={<PageLoader />}><AdminPage /></Suspense>
                </AdminRoute>
              }
            />
          </Route>
          {/* Catch-all 404 */}
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </ErrorBoundary>
      <Toaster />
    </ThemeProvider>
  )
}

export default App
