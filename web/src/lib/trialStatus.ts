// lib/trialStatus.ts — 순수 함수: 상태 코드 → UI 복사본 + 완료 플래그

const TERMINAL = new Set(['sent', 'fallback', 'expired', 'failed'])

/** 폴링 중단 여부: 터미널 상태이면 true */
export function isTerminal(s: string): boolean {
  return TERMINAL.has(s)
}

/** 상태 코드를 UI 텍스트 + done 플래그로 변환 (순수 함수, React 의존 없음) */
export function trialStatusMessage(status: string, published?: number): { text: string; done: boolean } {
  switch (status) {
    case 'verification_pending':
      return { text: '📧 확인 메일의 링크를 클릭하세요 (받은편지함/정크 확인).', done: false }
    case 'sending':
    case 'generating':
      return { text: '⏳ 브리핑 생성 중… (보통 1~5분). 이 창은 닫으셔도 됩니다.', done: false }
    case 'sent':
      return { text: `✅ 발송 완료! ${published ?? ''}건 — 받은편지함을 확인하세요.`, done: true }
    case 'fallback':
      return { text: '오늘은 검증 통과한 새 소식이 부족해 안내 메일을 보냈어요.', done: true }
    case 'expired':
      return { text: '확인 시간이 지났어요 — 다시 시도해주세요.', done: true }
    case 'failed':
      return { text: '문제가 생겼어요 — 잠시 후 다시 시도해주세요.', done: true }
    default:
      return { text: '처리 중…', done: false }
  }
}
