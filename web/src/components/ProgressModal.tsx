// web/src/components/ProgressModal.tsx — 중앙 모달 진행 표시(항상 닫기 가능; 닫아도 백그라운드 계속).
import { useEffect, useRef } from 'react'

interface Props { title: string; text: string; busy: boolean; elapsedSec: number; onClose: () => void }

export function ProgressModal({ title, text, busy, elapsedSec, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  const mm = Math.floor(elapsedSec / 60), ss = String(elapsedSec % 60).padStart(2, '0')
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
      <div role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}
        style={{ background: '#fff', borderRadius: 12, padding: '24px 28px', maxWidth: 440, width: '90%',
          boxShadow: '0 12px 48px rgba(0,0,0,0.28)', textAlign: 'center' }}>
        <h3 style={{ margin: '0 0 14px', fontSize: 17 }}>{title}</h3>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', justifyContent: 'center', fontSize: 15 }}>
          {busy && <span aria-hidden style={{ fontSize: 22, animation: 'spin 1s linear infinite' }}>⏳</span>}
          <div>{text}</div>
        </div>
        {busy && <div style={{ fontSize: 13, color: '#789', marginTop: 8 }}>{mm}:{ss} 경과</div>}
        {busy && <p style={{ fontSize: 12, color: '#999', marginTop: 14 }}>💡 창을 닫아도 계속 생성돼 메일로 도착합니다.</p>}
        <button ref={closeRef} type="button" onClick={onClose}
          style={{ marginTop: 18, padding: '9px 22px', fontSize: 14, borderRadius: 8, cursor: 'pointer' }}>닫기</button>
      </div>
    </div>
  )
}
