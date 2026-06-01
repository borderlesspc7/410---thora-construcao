import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    dedupe: ["react", "react-dom"],
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8001",
        changeOrigin: true,
      },
    },
    port: 8000,
    strictPort: true,
    // HMR na mesma porta do dev server (evita ws://localhost:5173 → 400)
    hmr: {
      protocol: "ws",
      host: "localhost",
      port: 8000,
      clientPort: 8000,
    },
  },
})
