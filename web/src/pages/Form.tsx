// web/src/pages/Form.tsx — 미디어(MAX5)·발송시각(6/7/8 KST)·이메일 수집. 체험/구독 버튼은 v1.0 비활성.
import { useEffect, useState } from 'react'
import { fetchCatalog, postTrial, getProfile, putProfile } from '../api'
import { isAuthed } from '../auth/session'
import { startLogin } from '../auth/login'
import type { Catalog } from '../types'
import { SourcePicker } from '../components/SourcePicker'

export default function Form() {
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const [sendHour, setSendHour] = useState(7)
  const [email, setEmail] = useState('')
  const [msg, setMsg] = useState('')
  const [recipient, setRecipient] = useState<string | null>(null)
  const [authed, setAuthed] = useState(false)

  useEffect(() => {
    fetchCatalog().then(setCatalog).catch((e) => setError(String(e)))
    setAuthed(isAuthed())
    if (isAuthed()) {
      getProfile().then((p) => setRecipient(p.recipient || null)).catch((e) => console.error('Failed to get profile:', e))
    }
  }, [])

  if (error) return <p style={{ color: '#c00' }}>카탈로그를 불러오지 못했습니다: {error}</p>
  if (!catalog) return <p>불러오는 중…</p>

  return (
    <div>
      <h1 style={{ fontSize: 22 }}>구독 설정</h1>
      <h2 style={{ fontSize: 16 }}>1. 미디어 선택 <span style={{ color: '#999', fontSize: 13 }}>(최대 {catalog.max_sources}개)</span></h2>
      <SourcePicker categories={catalog.categories} max={catalog.max_sources} selected={selected} onChange={setSelected} />

      <h2 style={{ fontSize: 16 }}>2. 발송 시각 (KST)</h2>
      <div>
        {catalog.send_hours.map((h) => {
          const hh = String(h).padStart(2, '0')
          return (
            <label key={h} style={{ marginRight: 16 }}>
              <input
                type="radio"
                name="sendHour"
                aria-label={`${hh}:00 KST`}
                checked={sendHour === h}
                onChange={() => setSendHour(h)}
              />{' '}
              {hh}:00
            </label>
          )
        })}
      </div>

      <h2 style={{ fontSize: 16 }}>3. 이메일</h2>
      {authed ? (
        <div style={{ padding: 8, fontSize: 14 }}>
          구독 주소: <strong>{recipient || '로딩 중…'}</strong>
        </div>
      ) : (
        <input
          type="email" value={email} placeholder="you@example.com"
          onChange={(e) => setEmail(e.target.value)}
          style={{ padding: 8, width: 280, fontSize: 14 }}
        />
      )}

      <div style={{ marginTop: 24, display: 'flex', gap: 12 }}>
        {authed ? (
          <button type="button" disabled={!selected.length}
            onClick={async () => {
              setMsg('구독 중…')
              try {
                const r = await putProfile({ sources: selected, send_hour: sendHour, lens: 'general', depth: 'summary' })
                const status = r.delivery === 'active'
                  ? '구독 완료 — 매일 발송'
                  : '구독 저장 — 메일의 SES 인증 클릭 후 발송'
                setMsg(status)
              } catch (e) {
                setMsg(`오류: ${String(e)}`)
              }
            }}
            style={{ padding: '10px 18px', fontSize: 14 }}>구독하기</button>
        ) : (
          <button type="button"
            onClick={() => startLogin()}
            style={{ padding: '10px 18px', fontSize: 14 }}>로그인 / 구독하기</button>
        )}
        <button type="button" disabled={!(selected.length && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email))}
          onClick={async () => {
            setMsg('보내는 중…')
            const r = await postTrial({ email, sources: selected, lens: 'general', depth: 'summary' })
            setMsg(r.status === 'verification_pending'
              ? '확인 메일을 보냈어요 — 메일의 링크를 클릭하면 곧 브리핑이 도착합니다.'
              : r.status === 'sending' ? '곧 브리핑이 도착합니다!' : (r.error || '잠시 후 다시 시도해주세요.'))
          }}
          style={{ padding: '10px 18px', fontSize: 14 }}>체험하기</button>
      </div>
      {msg && <p>{msg}</p>}
      <p style={{ fontSize: 12, color: '#999', marginTop: 8 }}>
        선택: {selected.length}개 출처 · {String(sendHour).padStart(2, '0')}:00 KST · {authed ? `${recipient || '로딩 중…'}` : email || '이메일 미입력'}
      </p>
    </div>
  )
}
