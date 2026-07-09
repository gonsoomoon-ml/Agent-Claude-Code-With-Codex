// web/src/pages/Admin.tsx — 관리자 발송 모니터링 대시보드(/admin).
// 신뢰 경계: 여기서의 isAdmin() 게이팅은 UX 편의(노출 제어)일 뿐 — 실제 집행은 backend require_admin(403).
import { useEffect, useState, type CSSProperties } from 'react'
import { isAdmin, isAuthed, authedFetch } from '../auth/session'
import { startLogin } from '../auth/login'

type Email = {
  user_id: string; recipient: string; run_date: string; sent_at: string
  published: number; quarantined: number; duration_ms: number; cost_usd: number
  status: string; message_id: string
}

type Totals = { count: number; cost_usd: number; avg_duration_ms: number }

const mins = (ms: number) => `${Math.floor(ms / 60000)}m${Math.round((ms % 60000) / 1000)}s`

const TH: CSSProperties = { textAlign: 'left', padding: '8px 10px', borderBottom: '1px solid var(--border)', color: 'var(--text-dim)', fontSize: 13 }
const TD: CSSProperties = { padding: '8px 10px', borderBottom: '1px solid var(--border)', fontSize: 14 }

export default function Admin() {
  const [rows, setRows] = useState<Email[]>([])
  const [totals, setTotals] = useState<Totals | null>(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!isAuthed()) {                                  // 토큰 없음(직접 로드/새로고침) → 로그인 시작
      sessionStorage.setItem('post_login', '/admin')    // 로그인 후 여기로 복귀(CallbackRedirect)
      startLogin()
      return
    }
    if (!isAdmin()) { setErr('관리자 전용'); return }    // 로그인은 됐으나 admins 그룹 아님
    authedFetch('/admin/emails')
      .then((r) => {
        if (!r.ok) throw new Error(`admin/emails ${r.status}`)
        return r.json()
      })
      .then((d) => {
        setRows(d.emails ?? [])
        setTotals(d.totals ?? null)
      })
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
              <td style={TD}>{e.published ?? 0}</td>
              <td style={TD}>{mins(e.duration_ms ?? 0)}</td>
              <td style={TD}>≈${(e.cost_usd ?? 0).toFixed(2)}</td>
              <td style={TD}>{e.status ?? ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {totals && (
        <p style={{ marginTop: 10, fontSize: 13, color: 'var(--text-dim)' }}>
          합계 · {totals.count}건 · ≈${(totals.cost_usd ?? 0).toFixed(2)} · 평균 {mins(totals.avg_duration_ms ?? 0)}
        </p>
      )}
    </div>
  )
}
