// web/src/App.tsx — 라우터(/, /setup, /admin) + OAuth 콜백 복귀 처리.
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import CallbackRedirect from './auth/CallbackRedirect'
import Landing from './pages/Landing'
import Form from './pages/Form'
import Admin from './pages/Admin'

export default function App() {
  return (
    <BrowserRouter>
      {/* Router 안쪽: 콜백 처리 후 post_login 경로로 client-side 복귀(메모리 토큰 보존) */}
      <CallbackRedirect />
      <div style={{ fontFamily: 'system-ui, -apple-system, sans-serif', maxWidth: 760, margin: '0 auto', padding: '24px 16px' }}>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/setup" element={<Form />} />
          <Route path="/admin" element={<Admin />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}
