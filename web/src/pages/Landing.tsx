// web/src/pages/Landing.tsx — 서비스 소개 + 정적 샘플 미리보기(GET /sample) + 설정 링크.
import { Link } from 'react-router-dom'
import { sampleUrl } from '../api'

export default function Landing() {
  return (
    <div>
      <h1 style={{ fontSize: 26 }}>매일 아침, 검증된 AI 브리핑</h1>
      <p style={{ color: '#444' }}>
        선택한 매체의 소식을 <strong>검증 후 발행(verify-before-publish)</strong> 파이프라인이
        독립 검증해 매일 정해진 시각에 이메일로 보냅니다. 확인되지 않은 주장은 표시에서 빠집니다.
      </p>
      <h2 style={{ fontSize: 18 }}>받아보시는 메일 예시</h2>
      <iframe title="샘플 브리핑" src={sampleUrl()} style={{ width: '100%', height: 380, border: '1px solid #eee', borderRadius: 8 }} />
      <div style={{ marginTop: 20 }}>
        <Link to="/setup" style={{ display: 'inline-block', padding: '12px 22px', background: '#1565c0', color: '#fff', borderRadius: 8, textDecoration: 'none' }}>
          구독 설정하기 →
        </Link>
      </div>
    </div>
  )
}
