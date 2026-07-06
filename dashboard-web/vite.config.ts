import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  base: '/dashboard/',
  server: { proxy: { '/dashboard/api': 'http://127.0.0.1:8787' } },
})
