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
    // ★ OAuth 콜백(?code)일 때만 동작한다. 일반 로드에서도 돌면, /admin 로드 시 Admin 이 방금
    //   심은 post_login 을 이 .then() 이 (Cognito 리다이렉트 전에) 지워버리는 레이스가 생긴다.
    if (!new URLSearchParams(location.search).has('code')) return
    handleCallback()
      .then(() => {
        const dest = sessionStorage.getItem('post_login')   // 로그인 전 가려던 곳
        sessionStorage.removeItem('post_login')
        navigate(dest || location.pathname, { replace: true })  // 복귀 or ?code 정리
      })
      .catch((e) => console.error('OAuth callback failed:', e))
  }, [navigate])
  return null
}
