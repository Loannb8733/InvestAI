import { QueryClient } from "@tanstack/react-query"
import { queryKeys } from "./queryKeys"

export function invalidateAllFinancialData(queryClient: QueryClient) {
  queryClient.invalidateQueries({ queryKey: queryKeys.portfolios.all })
  queryClient.invalidateQueries({ queryKey: queryKeys.assets.all })
  queryClient.invalidateQueries({ queryKey: queryKeys.transactions.all })
  queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all })
  queryClient.invalidateQueries({ queryKey: queryKeys.analytics.all })
}

export function invalidatePortfolioData(queryClient: QueryClient, portfolioId: string) {
  queryClient.invalidateQueries({ queryKey: queryKeys.portfolios.all })
  queryClient.invalidateQueries({ queryKey: queryKeys.portfolios.detail(portfolioId) })
  queryClient.invalidateQueries({ queryKey: queryKeys.portfolios.metrics(portfolioId) })
  queryClient.invalidateQueries({ queryKey: queryKeys.portfolios.history(portfolioId) })
  queryClient.invalidateQueries({ queryKey: queryKeys.assets.all })
  queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all })
}

export function invalidateAssetData(queryClient: QueryClient, assetId?: string) {
  queryClient.invalidateQueries({ queryKey: queryKeys.assets.all })
  if (assetId) {
    queryClient.invalidateQueries({ queryKey: queryKeys.assets.detail(assetId) })
  }
  queryClient.invalidateQueries({ queryKey: queryKeys.portfolios.all })
  queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all })
}

export function invalidateTransactionData(queryClient: QueryClient) {
  queryClient.invalidateQueries({ queryKey: queryKeys.transactions.all })
  queryClient.invalidateQueries({ queryKey: queryKeys.assets.all })
  queryClient.invalidateQueries({ queryKey: queryKeys.portfolios.all })
  queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all })
}

export function invalidateAlerts(queryClient: QueryClient) {
  queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all })
  queryClient.invalidateQueries({ queryKey: queryKeys.alerts.summary })
}

export function invalidateNotifications(queryClient: QueryClient) {
  queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all })
  queryClient.invalidateQueries({ queryKey: queryKeys.notifications.unreadCount })
}
