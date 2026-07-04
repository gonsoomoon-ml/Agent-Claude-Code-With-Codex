// web/src/pages/Form.tsx — 미디어(MAX5)·발송시각·이메일 수집 + 체험/구독 진행 UI (v1.1c)
import { useEffect, useRef, useState } from 'react'
import { fetchCatalog, postTrial, getTrialStatus, getProfile, putProfile } from '../api'
import { isAuthed } from '../auth/session'
import { startLogin } from '../auth/login'
import { trialStatusMessage, isTerminal } from '../lib/trialStatus'
import type { Catalog } from '../types'
import { SourcePicker } from '../components/SourcePicker'
import { ProgressModal } from '../components/ProgressModal'
import { coralPill, ghostPill, coralDisabled } from '../theme'

/** 10분 타임아웃: 3s 간격으로 최대 200회 폴링 */
const MAX_POLL_COUNT = 200

export default function Form() {
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const [sendHour, setSendHour] = useState(7)
  const [email, setEmail] = useState('')
  const [recipient, setRecipient] = useState<string | null>(null)
  const [authed, setAuthed] = useState(false)
  const [maxSources, setMaxSources] = useState<number | null>(null)

  // 진행 UI 상태
  const [submitting, setSubmitting] = useState<'trial' | 'subscribe' | null>(null)
  const [card, setCard] = useState<{ text: string; busy: boolean } | null>(null)
  const [elapsed, setElapsed] = useState(0)

  // 폴링·경과 인터벌 ref (언마운트 시 정리)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPolling = () => {
    if (pollRef.current !== null) { clearInterval(pollRef.current); pollRef.current = null }
    if (timerRef.current !== null) { clearInterval(timerRef.current); timerRef.current = null }
  }

  useEffect(() => {
    fetchCatalog().then(setCatalog).catch((e) => setError(String(e)))
    setAuthed(isAuthed())
    if (isAuthed()) {
      getProfile()
        .then((p) => { setRecipient(p.recipient || null); if (p.max_sources) setMaxSources(p.max_sources) })
        .catch((e) => console.error('Failed to get profile:', e))
    }
    return stopPolling // 언마운트 시 인터벌 정리
  }, [])

  // ── 체험하기 핸들러 ──────────────────────────────────────────
  const handleTrial = async () => {
    stopPolling() // M3: 재호출 시 이전 폴링 인터벌 고아 방지
    setSubmitting('trial')
    setElapsed(0)
    setCard({ text: '보내는 중…', busy: true })

    try {
      const r = await postTrial({ email, sources: selected, lens: 'general', depth: 'summary' })

      if (r.httpStatus !== 202) {
        // 비동기 처리 미시작 (에러 또는 즉시 응답)
        const { text } = trialStatusMessage(r.status || 'failed')
        setCard({ text: r.error || text, busy: false })
        setSubmitting(null)
        return
      }

      // HTTP 202 — 비동기 생성 시작: 초기 상태 표시 후 폴링 시작
      const init = trialStatusMessage(r.status || 'generating')
      setCard({ text: init.text, busy: !init.done })

      if (init.done) {
        // 드물게 즉시 완료 응답인 경우
        setSubmitting(null)
        return
      }

      // 경과 타이머 (1s)
      timerRef.current = setInterval(() => {
        setElapsed((e) => e + 1)
      }, 1000)

      // 폴링 인터벌 (3s)
      let pollCount = 0
      pollRef.current = setInterval(async () => {
        pollCount += 1

        if (pollCount > MAX_POLL_COUNT) {
          stopPolling()
          setCard({ text: '시간이 초과되었어요 — 잠시 후 다시 시도해주세요.', busy: false })
          setSubmitting(null)
          return
        }

        try {
          const s = await getTrialStatus(email)
          const { text, done } = trialStatusMessage(s.status, s.published)
          setCard({ text, busy: !done })

          if (isTerminal(s.status)) {
            stopPolling()
            setSubmitting(null)
          }
        } catch {
          // 일시적 네트워크 오류 — 다음 폴링에서 재시도
        }
      }, 3000)
    } catch (e) {
      setCard({ text: `오류: ${String(e)}`, busy: false })
      setSubmitting(null)
    }
  }

  // ── 구독하기 핸들러 ──────────────────────────────────────────
  const handleSubscribe = async () => {
    setSubmitting('subscribe')
    setElapsed(0)
    setCard({ text: '구독 중…', busy: true })

    try {
      const r = await putProfile({ sources: selected, send_hour: sendHour, lens: 'general', depth: 'summary' })
      const text =
        r.delivery === 'active'
          ? '구독 완료 — 매일 발송'
          : '구독 저장 — 메일의 SES 인증 클릭 후 발송'
      setCard({ text, busy: false })
    } catch (e) {
      setCard({ text: `오류: ${String(e)}`, busy: false })
    } finally {
      setSubmitting(null)
    }
  }

  if (error) return <p style={{ color: '#c00' }}>카탈로그를 불러오지 못했습니다: {error}</p>
  if (!catalog) return <p>불러오는 중…</p>

  const isTrialSubmitting = submitting === 'trial'
  const isSubSubmitting = submitting === 'subscribe'
  const trialDisabled = isTrialSubmitting || !(selected.length && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email))

  const maxSel = maxSources ?? catalog.max_sources

  return (
    <div>
      <h1 style={{ fontSize: 22 }}>구독 설정</h1>
      <h2 style={{ fontSize: 16 }}>1. 미디어 선택 <span style={{ color: '#999', fontSize: 13 }}>(최대 {maxSel}개)</span></h2>
      <SourcePicker categories={catalog.categories} max={maxSel} selected={selected} onChange={setSelected} />

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

      <div style={{ marginTop: 24, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <button
          type="button"
          className="cta-coral"
          disabled={trialDisabled}
          onClick={handleTrial}
          style={{ ...coralPill, ...(trialDisabled ? coralDisabled : null) }}
        >
          {isTrialSubmitting ? '보내는 중…' : <><span aria-hidden="true">▶</span> 체험하기</>}
        </button>
        {authed ? (
          <button
            type="button"
            className="cta-ghost"
            disabled={isSubSubmitting || !selected.length}
            onClick={handleSubscribe}
            style={ghostPill}
          >
            {isSubSubmitting ? '보내는 중…' : <>구독하기 <span aria-hidden="true">→</span></>}
          </button>
        ) : (
          <button
            type="button"
            className="cta-ghost"
            onClick={() => startLogin()}
            style={ghostPill}
          >
            로그인 / 구독하기 <span aria-hidden="true">→</span>
          </button>
        )}
      </div>

      {card && (
        <ProgressModal
          title={authed ? '구독' : '브리핑 체험'}
          text={card.text} busy={card.busy} elapsedSec={elapsed}
          onClose={() => { stopPolling(); setCard(null) }}
        />
      )}

      <p style={{ fontSize: 12, color: '#999', marginTop: 8 }}>
        선택: {selected.length}개 출처 · {String(sendHour).padStart(2, '0')}:00 KST · {authed ? `${recipient || '로딩 중…'}` : email || '이메일 미입력'}
      </p>
    </div>
  )
}
