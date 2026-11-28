import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: process.env.AINIEE_API_TARGET || 'http://127.0.0.1:8000',
        // Preserve the browser origin and Host for the API's same-origin bootstrap.
        changeOrigin: false,
      },
    },
  },
});
