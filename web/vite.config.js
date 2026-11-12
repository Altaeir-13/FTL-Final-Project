import { defineConfig } from 'vite';
export default defineConfig({
  base: './',
  publicDir: false,
  build: { target: 'es2022', sourcemap: false },
  server: { host: '127.0.0.1', port: 5173, strictPort: true },
});
