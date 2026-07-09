// OAuth 콜백 처리 후, 로그인 전 가려던 곳(sessionStorage 'post_login')으로 복귀시킨다.
// ★ 반드시 <BrowserRouter> 안쪽 컴포넌트여야 useNavigate 사용 가능 — navigate 는
//   전체 페이지 리로드 없이 이동하므로 방금 메모리에 담은 id_token 이 보존된다.
//   (window.location 으로 이동하면 새 JS 컨텍스트 → 메모리 토큰 소멸 → 재로그인 루프.)
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { handleCallback } from './callback'

export default function CallbackRedirect() {
  const navigate = useNavigate()
  useEffect(() => {
    handleCallback()
      .then(() => {
        const dest = sessionStorage.getItem('post_login')
        if (dest) {
          sessionStorage.removeItem('post_login')
          navigate(dest, { replace: true })
        }
      })
      .catch((e) => console.error('OAuth callback failed:', e))
  }, [navigate])
  return null
}
