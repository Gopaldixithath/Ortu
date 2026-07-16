import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Standalone ORTU Fitness site: served at the domain root ('/').
// In local dev, `npm run dev` proxies API calls to the FastAPI backend
// (run it separately on :8000). In production the FastAPI app serves the
// built assets, so this proxy is dev-only.
export default defineConfig({
  base: '/',
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/healthz': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
