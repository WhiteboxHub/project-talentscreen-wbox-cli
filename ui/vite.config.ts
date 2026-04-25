import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [react()],
    server: {
        port: 3000,
        proxy: {
            '/api': process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000',
            '/ws': {
                target: process.env.VITE_WS_PROXY_TARGET ?? 'ws://localhost:8000',
                ws: true,
            },
        }
    }
})
