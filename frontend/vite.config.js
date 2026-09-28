import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// Where the API gateway is running. `docker compose up` exposes it on port 8080.
const API_TARGET = process.env.API_URL || 'http://localhost:8080'
const proxy = { '/api': { target: API_TARGET, changeOrigin: true } }

export default defineConfig({
  // Relative asset paths, so the build works from any S3 bucket/prefix
  base: './',
  plugins: [react(), tailwindcss()],
  // In development (npm run dev / npm run preview), /api/* calls are forwarded to the gateway,
  // so the browser sees one origin and no CORS setup is needed.
  server: { proxy },
  preview: { proxy },
})
