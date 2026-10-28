import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    proxy: {
      '/api': 'http://127.0.0.1:8774',
      '/docs': 'http://127.0.0.1:8774',
      '/openapi.json': 'http://127.0.0.1:8774',
      '/research': 'http://127.0.0.1:8774',
    },
  },
});
