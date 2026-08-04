import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
  },
  server: {
    proxy: {
      // Proxy API + SSE calls to the FastAPI dev server so the frontend never needs
      // CORS config or a hardcoded backend origin during local development.
      '/query': 'http://localhost:8000',
      '/agent': 'http://localhost:8000',
      '/api': 'http://localhost:8000',
      '/metrics': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
