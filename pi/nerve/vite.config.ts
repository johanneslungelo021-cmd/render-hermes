import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3090,
    proxy: {
      '/a2a': {
        target: 'http://localhost:8087',
        changeOrigin: true,
      },
      '/api': {
        target: 'http://localhost:8087',
        changeOrigin: true,
      },
      '/.well-known': {
        target: 'http://localhost:8087',
        changeOrigin: true,
      },
    },
  },
})
