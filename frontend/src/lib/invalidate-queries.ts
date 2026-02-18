import { QueryClient } from "@tanstack/react-query"

export function invalidateAllFinancialData(queryClient: QueryClient) {
  queryClient.invalidateQueries({ queryKey: ["portfolios"] })
  queryClient.invalidateQueries({ queryKey: ["assets"] })
  queryClient.invalidateQueries({ queryKey: ["transactions"] })
  queryClient.invalidateQueries({ queryKey: ["dashboard"] })
  queryClient.invalidateQueries({ queryKey: ["snapshots"] })
}
