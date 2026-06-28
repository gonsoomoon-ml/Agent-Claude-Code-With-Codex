import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 로컬 dev: /catalog·/sample 을 로컬 API(uvicorn :8000)로 프록시 → CORS 불필요.
// 배포 빌드: VITE_API_BASE(절대 URL)로 직접 호출(앱레벨 CORS 가 허용).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/catalog': 'http://127.0.0.1:8000',
      '/sample': 'http://127.0.0.1:8000',
    },
  },
  test: { environment: 'jsdom', globals: true, setupFiles: ['./src/setupTests.ts'] },
})
