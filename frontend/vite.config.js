import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('/node_modules/@mui/') || id.includes('/node_modules/@emotion/')) {
            return 'mui'
          }
          if (id.includes('/node_modules/react') || id.includes('/node_modules/react-router-dom/')) {
            return 'react'
          }
        }
      },
    },
  },
})
