// web/src/pages/Form.tsx — 미디어(MAX5)·발송시각·이메일 수집 + 체험/구독 진행 UI (v1.1c)
import { useEffect, useRef, useState, type CSSProperties } from 'react'
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

// 2단 레이아웃(체험/구독) 스타일 — 시간성이 다른 두 행동(즉시 체험 vs 예약 구독)을 구조로 분리.
const STAGE: CSSProperties = { border: '1px solid var(--border)', borderRadius: 14, padding: '16px 18px', marginTop: 18, background: 'var(--stage)' }
const SHEAD: CSSProperties = { display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }
const SHEAD_H2: CSSProperties = { fontSize: 16, margin: 0 }
const BADGE_BASE: CSSProperties = { width: 24, height: 24, borderRadius: 9999, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 800, flexShrink: 0 }
const BADGE_ONE: CSSProperties = { ...BADGE_BASE, background: 'linear-gradient(135deg, var(--coral-from), var(--coral-to))', color: 'var(--coral-ink)' }
const BADGE_TWO: CSSProperties = { ...BADGE_BASE, background: 'var(--panel-2)', color: 'var(--text-dim)', border: '1px solid var(--border)' }
const SSUB: CSSProperties = { fontSize: 12, color: 'var(--text-dim)', margin: '2px 0 14px 34px' }
const ROWLABEL: CSSProperties = { fontSize: 14, fontWeight: 600, color: 'var(--text)', margin: '16px 0 6px' }

export default function Form() {
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const [sendHour, setSendHour] = useState(7)
  const [lens, setLens] = useState('general')
  const [depth, setDepth] = useState('summary')
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
        .then((p) => {
          setRecipient(p.recipient || null)
          if (p.max_sources) setMaxSources(p.max_sources)
          if (p.subscribed && p.profile) {
            const prof = p.profile
            if (Array.isArray(prof.sources)) setSelected(prof.sources as string[])
            if (typeof prof.send_hour === 'number') setSendHour(prof.send_hour)
            if (typeof prof.lens === 'string') setLens(prof.lens)
            if (typeof prof.depth === 'string') setDepth(prof.depth)
          }
        })
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
      const r = await putProfile({ sources: selected, send_hour: sendHour, lens, depth })
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

  if (error) return <p style={{ color: 'var(--danger)' }}>카탈로그를 불러오지 못했습니다: {error}</p>
  if (!catalog) return <p>불러오는 중…</p>

  const isTrialSubmitting = submitting === 'trial'
  const isSubSubmitting = submitting === 'subscribe'
  const trialDisabled = isTrialSubmitting || !(selected.length && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email))

  const maxSel = maxSources ?? catalog.max_sources

  return (
    <div>
      <h1 style={{ fontSize: 22 }}>구독 설정</h1>
      <p style={{ color: 'var(--text-dim)', fontSize: 13, margin: '0 0 20px' }}>
        먼저 매체를 고르고 → <strong>지금 바로 체험</strong>해 보세요. 마음에 들면 매일 구독을 설정하면 됩니다.
      </p>

      {/* 공통: 미디어 선택 — 체험·구독 모두 이 선택을 사용 */}
      <h2 style={{ fontSize: 16 }}>미디어 선택 <span style={{ color: 'var(--text-dim)', fontSize: 13, fontWeight: 400 }}>(최대 {maxSel}개 · 체험·구독 공통)</span></h2>
      <SourcePicker categories={catalog.categories} max={maxSel} selected={selected} onChange={setSelected} />

      {/* ① 지금 체험 — 즉시 발송(예약 아님). 필요한 것: 매체 + 이메일 */}
      <section style={STAGE}>
        <div style={SHEAD}><span aria-hidden="true" style={BADGE_ONE}>▶</span><h2 style={SHEAD_H2}>지금 체험</h2></div>
        <p style={SSUB}>선택한 매체로 <strong>지금 한 통</strong> 받아봅니다 — 예약 아님, 즉시 발송.</p>
        {authed ? (
          <div style={{ fontSize: 14 }}>구독 주소: <strong>{recipient || '로딩 중…'}</strong></div>
        ) : (
          <>
            <div style={ROWLABEL}>이메일</div>
            <input
              type="email" value={email} placeholder="you@example.com"
              onChange={(e) => setEmail(e.target.value)}
              style={{ padding: 8, width: 300, maxWidth: '100%', fontSize: 14 }}
            />
          </>
        )}
        <div style={{ marginTop: 16 }}>
          <button
            type="button"
            className="cta-coral"
            disabled={trialDisabled}
            onClick={handleTrial}
            style={{ ...coralPill, ...(trialDisabled ? coralDisabled : null) }}
          >
            {isTrialSubmitting ? '보내는 중…' : <><span aria-hidden="true">▶</span> 체험하기</>}
          </button>
        </div>
      </section>

      {/* ② 매일 구독 설정 — 예약 발송(로그인 필요). 발송 시각·관점·깊이 */}
      <section style={STAGE}>
        <div style={SHEAD}><span aria-hidden="true" style={BADGE_TWO}>2</span><h2 style={SHEAD_H2}>매일 구독 설정</h2></div>
        <p style={SSUB}>마음에 들면 <strong>매일 정해진 시각</strong>에 자동 발송. (로그인 필요)</p>

        <div style={ROWLABEL}>발송 시각 (KST)</div>
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

        <div style={ROWLABEL}>관점 (렌즈)</div>
        <div>
          {catalog.lenses.map((l) => (
            <label key={l.key} style={{ marginRight: 16 }}>
              <input
                type="radio"
                name="lens"
                aria-label={l.name}
                checked={lens === l.key}
                onChange={() => setLens(l.key)}
              />{' '}
              {l.name}
            </label>
          ))}
        </div>

        <div style={ROWLABEL}>깊이</div>
        <div>
          {catalog.depths.map((d) => (
            <label key={d} style={{ marginRight: 16 }}>
              <input
                type="radio"
                name="depth"
                aria-label={d}
                checked={depth === d}
                onChange={() => setDepth(d)}
              />{' '}
              {d}
            </label>
          ))}
        </div>

        <div style={{ marginTop: 16 }}>
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
      </section>

      {card && (
        <ProgressModal
          title={authed ? '구독' : '브리핑 체험'}
          text={card.text} busy={card.busy} elapsedSec={elapsed}
          onClose={() => { stopPolling(); setCard(null) }}
        />
      )}

      <p style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 12 }}>
        선택: {selected.length}개 출처 · {String(sendHour).padStart(2, '0')}:00 KST · {authed ? `${recipient || '로딩 중…'}` : email || '이메일 미입력'}
      </p>
    </div>
  )
}
