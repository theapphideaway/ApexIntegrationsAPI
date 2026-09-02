import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Served by Django at https://www.apexintegrations.ai/portal/ — same origin
// as the API, so no CORS and no separate hosting.
export default defineConfig({
  plugins: [react()],
  base: '/portal/',
  build: { outDir: 'dist', emptyOutDir: true },
  server: { proxy: { '/api': 'https://www.apexintegrations.ai' } },
})
