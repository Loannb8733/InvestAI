import ReactDOM from 'react-dom/client'
import { QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { toast } from '@/hooks/use-toast'
import './index.css'

const queryClient = new QueryClient({
  // Global safety net: any query that fails (and isn't handling its own error
  // UI) surfaces a toast, so a failed fetch never leaves a silent blank screen.
  // Pages with bespoke error states opt out via meta.suppressGlobalError.
  // TOAST_LIMIT is 1, so simultaneous failures collapse to a single toast.
  queryCache: new QueryCache({
    onError: (_error, query) => {
      if (query.meta?.suppressGlobalError) return
      toast({
        variant: 'destructive',
        title: 'Erreur de chargement',
        description: 'Impossible de récupérer les données. Vérifiez votre connexion et réessayez.',
      })
    },
  }),
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      retry: 1,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <QueryClientProvider client={queryClient}>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </QueryClientProvider>
)
