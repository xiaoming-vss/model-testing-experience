import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8080'

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      host: '127.0.0.1',
      proxy: {
        '/v1': {
          target: apiTarget,
          changeOrigin: true,
        },
        '/__document_preview_proxy': {
          target: apiTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/__document_preview_proxy/, ''),
        },
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: './src/test/setup.ts',
      css: true,
      testTimeout: 30_000,
      // 页面测试是重型 jsdom 渲染，并发过高会互相抢 CPU 造成超时抖动；限制 worker 数。
      maxWorkers: 4,
    },
  }
})
