import { Navigate, Route, Routes } from 'react-router'
import Layout from '@/components/layout/Layout'
import { lazyWithRetry } from '@/lib/lazyWithRetry'
import ForgotPasswordPage from '@/pages/ForgotPasswordPage'
import LoginPage from '@/pages/LoginPage'
import NotFoundPage from '@/pages/NotFoundPage'
import RegisterPage from '@/pages/RegisterPage'
import ResetPasswordPage from '@/pages/ResetPasswordPage'
import { AdminRoute, LazyPage, PrivateRoute } from './guards'

const MasterDashboardPage = lazyWithRetry(() => import('@/pages/MasterDashboardPage'))
const DashboardPage = lazyWithRetry(() => import('@/pages/DashboardPage'))
const PortfolioUnifiedPage = lazyWithRetry(() => import('@/pages/PortfolioUnifiedPage'))
const IntelligencePage = lazyWithRetry(() => import('@/pages/IntelligencePage'))
const StrategyPage = lazyWithRetry(() => import('@/pages/StrategyPage'))
const ReportsPage = lazyWithRetry(() => import('@/pages/ReportsPage'))
const SettingsPage = lazyWithRetry(() => import('@/pages/SettingsPage'))
const AdminPage = lazyWithRetry(() => import('@/pages/AdminPage'))
const NotesPage = lazyWithRetry(() => import('@/pages/NotesPage'))
const CalendarPage = lazyWithRetry(() => import('@/pages/CalendarPage'))
const CrowdfundingMesProjectsPage = lazyWithRetry(() => import('@/pages/CrowdfundingMesProjectsPage'))
const CrowdfundingAuditLabPage = lazyWithRetry(() => import('@/pages/CrowdfundingAuditLabPage'))

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route
        path="/"
        element={
          <PrivateRoute>
            <Layout />
          </PrivateRoute>
        }
      >
        <Route index element={<LazyPage><MasterDashboardPage /></LazyPage>} />
        <Route path="portfolio" element={<LazyPage><PortfolioUnifiedPage /></LazyPage>} />
        <Route path="intelligence" element={<LazyPage><IntelligencePage /></LazyPage>} />
        <Route path="goals" element={<LazyPage><StrategyPage /></LazyPage>} />
        <Route path="reports" element={<LazyPage><ReportsPage /></LazyPage>} />
        <Route path="notes" element={<LazyPage><NotesPage /></LazyPage>} />
        <Route path="calendar" element={<LazyPage><CalendarPage /></LazyPage>} />
        <Route path="crowdfunding" element={<LazyPage><CrowdfundingMesProjectsPage /></LazyPage>} />
        <Route path="crowdfunding/audit-lab" element={<LazyPage><CrowdfundingAuditLabPage /></LazyPage>} />
        <Route path="crypto" element={<LazyPage><DashboardPage /></LazyPage>} />
        <Route path="transactions" element={<Navigate to="/portfolio?tab=transactions" replace />} />
        <Route path="exchanges" element={<Navigate to="/portfolio?tab=exchanges" replace />} />
        <Route path="analytics" element={<Navigate to="/intelligence?tab=analytics" replace />} />
        <Route path="alerts" element={<Navigate to="/intelligence?tab=alerts" replace />} />
        <Route path="predictions" element={<Navigate to="/intelligence?tab=predictions" replace />} />
        <Route path="strategies" element={<Navigate to="/intelligence?tab=decisions" replace />} />
        <Route path="insights" element={<Navigate to="/intelligence" replace />} />
        <Route path="smart-insights" element={<Navigate to="/intelligence?tab=smart" replace />} />
        <Route path="simulations" element={<Navigate to="/goals?tab=simulations" replace />} />
        <Route path="strategy" element={<Navigate to="/goals" replace />} />
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
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
