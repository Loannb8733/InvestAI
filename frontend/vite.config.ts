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
    include: ['react', 'react-dom', 'react-router-dom', 'react/jsx-runtime'],
  },
  server: {
    port: 3000,
    host: true,
    allowedHosts: 'all',
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
