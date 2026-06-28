// components/StatusCard.tsx — 진행 상태 카드 (스피너 + 경과 시간 + 메시지)

interface Props {
  text: string
  busy: boolean
  elapsedSec: number
}

export function StatusCard({ text, busy, elapsedSec }: Props) {
  const mm = Math.floor(elapsedSec / 60)
  const ss = String(elapsedSec % 60).padStart(2, '0')
  return (
    <div
      role="status"
      style={{
        marginTop: 16, padding: '12px 16px',
        border: '1px solid #cfe', background: '#f3f9ff',
        borderRadius: 8, display: 'flex', gap: 10, alignItems: 'center',
      }}
    >
      {busy && <span aria-hidden style={{ animation: 'spin 1s linear infinite' }}>⏳</span>}
      <div>
        <div style={{ fontSize: 14 }}>{text}</div>
        {busy && <div style={{ fontSize: 12, color: '#789' }}>{mm}:{ss} 경과</div>}
      </div>
    </div>
  )
}
