import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import mockPlugin from './mock/index.js'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const useMock = env.VITE_USE_MOCK !== 'false'
  const apiBase = env.VITE_API_BASE || 'http://127.0.0.1:8000'

  return {
    plugins: [vue(), ...(useMock ? [mockPlugin()] : [])],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      }
    },
    server: {
      host: '127.0.0.1',
      port: 5173,
      proxy: useMock
        ? undefined
        : {
            '/api': {
              target: apiBase,
              changeOrigin: true
            }
          }
    },
    build: {
      outDir: 'dist',
      sourcemap: false
    }
  }
})
