import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Local-only development server. It binds to 127.0.0.1 and proxies API
// requests to Django, so the browser sees a single origin (no CORS package
// required) and nothing is exposed to the network. Media files are not
// proxied: driver photos are streamed by the authenticated Django API only.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
})
