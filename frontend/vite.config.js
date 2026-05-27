import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],

  // react-pdf uses PDF.js which requires a Web Worker.
  // Vite needs to know how to resolve the worker file from pdfjs-dist.
  optimizeDeps: {
    include: ['react-pdf']
  },

  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
