// web/src/pages/Admin.tsx — 관리자 발송 모니터링 대시보드(/admin).
// 신뢰 경계: 여기서의 isAdmin() 게이팅은 UX 편의(노출 제어)일 뿐 — 실제 집행은 backend require_admin(403).
import { useEffect, useState, type CSSProperties } from 'react'
import { isAdmin, authedFetch } from '../auth/session'

type Email = {
  user_id: string; recipient: string; run_date: string; sent_at: string
  published: number; quarantined: number; duration_ms: number; cost_usd: number
  status: string; message_id: string
}

const mins = (ms: number) => `${Math.floor(ms / 60000)}m${Math.round((ms % 60000) / 1000)}s`

const TH: CSSProperties = { textAlign: 'left', padding: '8px 10px', borderBottom: '1px solid var(--border)', color: 'var(--text-dim)', fontSize: 13 }
const TD: CSSProperties = { padding: '8px 10px', borderBottom: '1px solid var(--border)', fontSize: 14 }

export default function Admin() {
  const [rows, setRows] = useState<Email[]>([])
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!isAdmin()) { setErr('관리자 전용'); return }
    authedFetch(`${import.meta.env.VITE_API_BASE}/admin/emails`)
      .then((r) => r.json())
      .then((d) => setRows(d.emails ?? []))
      .catch(() => setErr('불러오기 실패'))
  }, [])

  if (err) return <p style={{ color: 'var(--danger)' }}>{err}</p>

  return (
    <div>
      <h1 style={{ fontSize: 22 }}>관리자 · 발송 이메일</h1>
      <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 12 }}>
        <thead>
          <tr>
            <th style={TH}>수신자</th>
            <th style={TH}>발송시각</th>
            <th style={TH}>기사</th>
            <th style={TH}>소요</th>
            <th style={TH}>비용</th>
            <th style={TH}>상태</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((e) => (
            <tr key={`${e.user_id}-${e.run_date}`}>
              <td style={TD}>{e.recipient}</td>
              <td style={TD}>{e.sent_at}</td>
              <td style={TD}>{e.published}</td>
              <td style={TD}>{mins(e.duration_ms)}</td>
              <td style={TD}>≈${e.cost_usd.toFixed(2)}</td>
              <td style={TD}>{e.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
