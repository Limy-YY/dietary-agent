import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import mockPlugin from './mock/index.js'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const useMock = env.VITE_USE_MOCK !== 'false'
  const apiBase = env.VITE_API_BASE || 'http://127.0.0.1:8000'

  return {
    plugins: [
      vue(),
      // Element Plus 按需引入（IMP-005）：模板组件与 ElMessage/ElMessageBox 的样式
      // 由两个 unplugin 解析器按需注入，不再整包引入 element-plus/dist/index.css。
      AutoImport({ resolvers: [ElementPlusResolver()], dts: false }),
      Components({ resolvers: [ElementPlusResolver()], dts: false }),
      ...(useMock ? [mockPlugin()] : [])
    ],
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
