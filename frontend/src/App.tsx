import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { ThemeProvider } from '@/components/theme-provider'
import { Toaster } from '@/components/ui/toaster'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import Layout from '@/components/layout/Layout'
import LoginPage from '@/pages/LoginPage'
import RegisterPage from '@/pages/RegisterPage'
import NotFoundPage from '@/pages/NotFoundPage'
import ForgotPasswordPage from '@/pages/ForgotPasswordPage'
import ResetPasswordPage from '@/pages/ResetPasswordPage'
import DashboardPage from '@/pages/DashboardPage'
import PortfolioPage from '@/pages/PortfolioPage'
import TransactionsPage from '@/pages/TransactionsPage'
import ExchangesPage from '@/pages/ExchangesPage'
import AnalyticsPage from '@/pages/AnalyticsPage'
import AlertsPage from '@/pages/AlertsPage'
import PredictionsPage from '@/pages/PredictionsPage'
import ReportsPage from '@/pages/ReportsPage'
import SettingsPage from '@/pages/SettingsPage'
import AdminPage from '@/pages/AdminPage'
import NotesPage from '@/pages/NotesPage'
import CalendarPage from '@/pages/CalendarPage'
import SimulationsPage from '@/pages/SimulationsPage'
import InsightsPage from '@/pages/InsightsPage'
import GoalsPage from '@/pages/GoalsPage'
import SmartInsightsPage from '@/pages/SmartInsightsPage'
import VerifyEmailPage from '@/pages/VerifyEmailPage'

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" />
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, user } = useAuthStore()
  if (!isAuthenticated) return <Navigate to="/login" />
  if (user?.role !== 'admin') return <Navigate to="/" />
  return <>{children}</>
}

function App() {
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
            <Route index element={<DashboardPage />} />
            <Route path="portfolio" element={<PortfolioPage />} />
            <Route path="transactions" element={<TransactionsPage />} />
            <Route path="exchanges" element={<ExchangesPage />} />
            <Route path="analytics" element={<AnalyticsPage />} />
            <Route path="alerts" element={<AlertsPage />} />
            <Route path="predictions" element={<PredictionsPage />} />
            <Route path="reports" element={<ReportsPage />} />
            <Route path="notes" element={<NotesPage />} />
            <Route path="calendar" element={<CalendarPage />} />
            <Route path="simulations" element={<SimulationsPage />} />
            <Route path="insights" element={<InsightsPage />} />
            <Route path="smart-insights" element={<SmartInsightsPage />} />
            <Route path="goals" element={<GoalsPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route
              path="admin"
              element={
                <AdminRoute>
                  <AdminPage />
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
