import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import svgr from 'vite-plugin-svgr'
import path from 'path'

export default defineConfig({
  plugins: [
    // Unique-ify SVG IDs per file so Meteocons gradients don't collide when
    // multiple icons are rendered on the same page (id="a", id="b" conflicts).
    // @svgr/plugin-svgo runs SVGO before JSX transform; prefixIds makes every
    // gradient/symbol/filter ID unique based on the filename hash.
    svgr({
      svgrOptions: {
        plugins: ['@svgr/plugin-svgo', '@svgr/plugin-jsx'],
        svgoConfig: {
          plugins: [
            { name: 'preset-default' },
            { name: 'prefixIds' },
          ],
        },
      },
    }),
    react(),
    tailwindcss(),
  ],
  build: {},
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: true,   // bind 0.0.0.0 — expone en red local y Tailscale
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
