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
const MasterDashboardPage = lazy(() => import('@/pages/MasterDashboardPage'))
const DashboardPage = lazy(() => import('@/pages/DashboardPage'))
const PortfolioUnifiedPage = lazy(() => import('@/pages/PortfolioUnifiedPage'))
const IntelligencePage = lazy(() => import('@/pages/IntelligencePage'))
const StrategyPage = lazy(() => import('@/pages/StrategyPage'))
const ReportsPage = lazy(() => import('@/pages/ReportsPage'))
const SettingsPage = lazy(() => import('@/pages/SettingsPage'))
const AdminPage = lazy(() => import('@/pages/AdminPage'))
const NotesPage = lazy(() => import('@/pages/NotesPage'))
const CalendarPage = lazy(() => import('@/pages/CalendarPage'))
const CrowdfundingMesProjectsPage = lazy(() => import('@/pages/CrowdfundingMesProjectsPage'))
const CrowdfundingAuditLabPage = lazy(() => import('@/pages/CrowdfundingAuditLabPage'))

function PageLoader() {
  return (
    <div className="flex items-center justify-center h-[50vh]">
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
    </div>
  )
}

function LazyPage({ children }: { children: React.ReactNode }) {
  return (
    <ErrorBoundary>
      <Suspense fallback={<PageLoader />}>{children}</Suspense>
    </ErrorBoundary>
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
            {/* Main routes */}
            <Route index element={<LazyPage><MasterDashboardPage /></LazyPage>} />
            <Route path="portfolio" element={<LazyPage><PortfolioUnifiedPage /></LazyPage>} />
            <Route path="intelligence" element={<LazyPage><IntelligencePage /></LazyPage>} />
            <Route path="strategy" element={<LazyPage><StrategyPage /></LazyPage>} />
            <Route path="reports" element={<LazyPage><ReportsPage /></LazyPage>} />
            <Route path="notes" element={<LazyPage><NotesPage /></LazyPage>} />
            <Route path="calendar" element={<LazyPage><CalendarPage /></LazyPage>} />
            <Route path="crowdfunding" element={<LazyPage><CrowdfundingMesProjectsPage /></LazyPage>} />
            <Route path="crowdfunding/audit-lab" element={<LazyPage><CrowdfundingAuditLabPage /></LazyPage>} />

            {/* Redirects from old URLs */}
            <Route path="crypto" element={<LazyPage><DashboardPage /></LazyPage>} />
            <Route path="transactions" element={<Navigate to="/portfolio?tab=transactions" replace />} />
            <Route path="exchanges" element={<Navigate to="/portfolio?tab=exchanges" replace />} />
            <Route path="analytics" element={<Navigate to="/intelligence?tab=analytics" replace />} />
            <Route path="alerts" element={<Navigate to="/intelligence?tab=alerts" replace />} />
            <Route path="predictions" element={<Navigate to="/intelligence?tab=predictions" replace />} />
            <Route path="insights" element={<Navigate to="/intelligence" replace />} />
            <Route path="smart-insights" element={<Navigate to="/intelligence?tab=smart" replace />} />
            <Route path="simulations" element={<Navigate to="/strategy?tab=simulations" replace />} />
            <Route path="goals" element={<Navigate to="/strategy" replace />} />
            <Route path="crowdfunding/projects" element={<Navigate to="/crowdfunding?tab=projects" replace />} />
            <Route path="crowdfunding/performance" element={<Navigate to="/crowdfunding?tab=performance" replace />} />
            <Route path="settings" element={<LazyPage><SettingsPage /></LazyPage>} />
            <Route
              path="admin"
              element={
                <AdminRoute>
                  <LazyPage><AdminPage /></LazyPage>
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
