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
            : {}),
        },
    proxy: {
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/setupTests.ts',
    css: true,
  },
})
