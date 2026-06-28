// web/src/App.tsx — 라우터(/, /setup).
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Landing from './pages/Landing'
import Form from './pages/Form'

export default function App() {
  return (
    <BrowserRouter>
      <div style={{ fontFamily: 'system-ui, -apple-system, sans-serif', maxWidth: 760, margin: '0 auto', padding: '24px 16px' }}>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/setup" element={<Form />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}
