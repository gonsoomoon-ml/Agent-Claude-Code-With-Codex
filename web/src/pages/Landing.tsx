// web/src/pages/Landing.tsx — 서비스 소개 + 정적 샘플 미리보기(GET /sample) + 설정 링크.
import { Link } from 'react-router-dom'
import { sampleUrl } from '../api'
import { coralPill } from '../theme'

export default function Landing() {
  return (
    <div>
      <h1 style={{ fontSize: 26 }}>매일 아침, 검증된 AI 브리핑</h1>
      <p style={{ color: 'var(--text-body)' }}>
        선택한 매체의 소식을 <strong>검증 후 발행(verify-before-publish)</strong> 파이프라인이
        독립 검증해 매일 정해진 시각에 이메일로 보냅니다. 확인되지 않은 주장은 표시에서 빠집니다.
      </p>
      <h2 style={{ fontSize: 18 }}>받아보시는 메일 예시</h2>
      {/* 이메일은 태생이 라이트 — 다크 위에 흰 사각형이 뜨는 대신 "미리보기 · 샘플 메일"
          라벨을 단 종이/디바이스 목업(패널)으로 감싸 '의도된 흰 문서'로 읽히게 한다. */}
      <div style={{ background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: 12, padding: 12, marginTop: 8 }}>
        <div style={{ fontSize: 11, letterSpacing: 0.6, textTransform: 'uppercase', color: 'var(--text-dim)', marginBottom: 8 }}>미리보기 · 샘플 메일</div>
        <iframe title="샘플 브리핑" src={sampleUrl()} style={{ width: '100%', height: 380, border: 'none', borderRadius: 8, background: '#fff', display: 'block' }} />
      </div>
      <div style={{ marginTop: 20 }}>
        <Link to="/setup" className="cta-coral" style={coralPill}>
          구독 설정하기 <span aria-hidden="true">→</span>
        </Link>
      </div>
    </div>
  )
}
