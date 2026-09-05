import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
    dedupe: ['react', 'react-dom'],
  },
  build: {
    rollupOptions: {
      output: {
        // Split heavy, stable vendors into their own long-cacheable chunks so
        // the entry bundle (and the login page) no longer ships charts/motion.
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (/[\\/]node_modules[\\/](react|react-dom|react-router|react-router-dom|scheduler)[\\/]/.test(id))
            return 'react-vendor'
          if (id.includes('@tanstack')) return 'query'
          if (/[\\/]node_modules[\\/](@nivo|d3-|lightweight-charts)/.test(id)) return 'charts'
          if (id.includes('framer-motion')) return 'motion'
          if (id.includes('@radix-ui')) return 'radix'
          return undefined
        },
      },
    },
  },
  optimizeDeps: {
    // Toutes les dépendances applicatives sont pré-bundlées au démarrage.
    //
    // Les pages sont montées en `React.lazy` : une dépendance absente de cette
    // liste n'est découverte qu'à la première visite de la page qui l'importe.
    // Vite l'optimise alors à la volée, sous un nouveau hash de cache — et la
    // sert avec sa propre copie de React. L'application se retrouve avec deux
    // instances, `useContext` lit `null`, et la page tombe dans l'ErrorBoundary
    // avec « Invalid hook call ». C'est arrivé sur `@radix-ui/react-tabs` à la
    // première ouverture de /portfolio, alors que /login et le dashboard
    // fonctionnaient : le défaut ne se voit qu'en visitant une page neuve.
    //
    // `dedupe` ne suffit pas : il résout les doublons du graphe de modules, pas
    // ceux que crée une seconde passe d'optimisation.
    include: [
      '@hookform/resolvers/zod',
      '@nivo/bar',
      '@nivo/line',
      '@nivo/pie',
      '@nivo/radar',
      '@radix-ui/react-alert-dialog',
      '@radix-ui/react-checkbox',
      '@radix-ui/react-dialog',
      '@radix-ui/react-dropdown-menu',
      '@radix-ui/react-label',
      '@radix-ui/react-popover',
      '@radix-ui/react-select',
      '@radix-ui/react-slider',
      '@radix-ui/react-slot',
      '@radix-ui/react-switch',
      '@radix-ui/react-tabs',
      '@radix-ui/react-toast',
      '@radix-ui/react-tooltip',
      '@tanstack/react-query',
      'axios',
      'class-variance-authority',
      'clsx',
      'cmdk',
      'framer-motion',
      'lightweight-charts',
      'lucide-react',
      'react',
      'react-dom',
      'react-dom/client',
      'react-dropzone',
      'react-hook-form',
      'react-router-dom',
      'react/jsx-runtime',
      'tailwind-merge',
      'zod',
      'zustand',
      'zustand/middleware',
    ],
  },
  server: {
    port: 3000,
    host: true,
    // `true`, pas 'all' : cette dernière est la syntaxe Vite 6. En Vite 5 la
    // valeur inattendue faisait échouer la vérification d'origine ajoutée pour
    // le HMR (handshake websocket rejeté en 400), ce qui avait conduit à
    // désactiver le HMR plutôt qu'à le réparer.
    allowedHosts: true,
    watch: {
      usePolling: true,
    },
    hmr: process.env.VITE_HMR_DISABLE === 'true'
      ? false
      : {
          ...(process.env.VITE_HMR_PROTOCOL === 'wss'
            ? { clientPort: 443, protocol: 'wss' as const }
            : {
                host: 'localhost',
                // Pas de clientPort en dur : sans valeur explicite, Vite
                // utilise le port réellement écouté (y compris après un
                // auto-incrément 3000→3001→…). Un fallback codé en dur
                // provoquait une boucle websocket-mort → full reload quand
                // le port par défaut était occupé (ex: container Docker).
                ...(process.env.VITE_HMR_PORT
                  ? { clientPort: Number(process.env.VITE_HMR_PORT) }
                  : {}),
              }),
        },
    proxy: {
      '/api': {
        // Defaults to the Docker Compose service name; override with
        // VITE_PROXY_TARGET=http://localhost:8000 when running Vite on the host.
        target: process.env.VITE_PROXY_TARGET || 'http://backend:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/setupTests.ts',
    css: true,
    env: {
      NODE_ENV: 'test',
    },
  },
})
