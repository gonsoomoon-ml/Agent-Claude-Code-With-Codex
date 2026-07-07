// web/src/theme.ts — v1.2: 웜 잉크 다크 테마 + 시그니처 코랄 pill CTA 토큰.
// 팔레트 원천은 index.html 의 :root CSS 변수(var(--bg/panel/text-body …)) — 여기선 그 변수를 참조만 한다.
// base look 은 인라인 스프레드, hover/disabled-glyph 는 index.html 의 전역 <style>.
import type { CSSProperties } from 'react'

export const colors = {
  coralFrom: '#FF9E80', coralTo: '#FF6B47', coralInk: '#1A0F0A',
  ghostBorder: 'rgba(255,255,255,0.22)', ghostText: 'var(--text-body)',
  coralWash: 'var(--coral-wash)',
}

export const coralPill: CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 8,
  borderRadius: 9999, padding: '14px 28px', fontSize: 16, fontWeight: 600,
  color: colors.coralInk,
  background: `linear-gradient(135deg, ${colors.coralFrom} 0%, ${colors.coralTo} 100%)`,
  border: '1px solid transparent', cursor: 'pointer', textDecoration: 'none',
  boxShadow: '0 1px 2px rgba(0,0,0,0.08)',
}

export const ghostPill: CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 8,
  borderRadius: 9999, padding: '12px 22px', fontSize: 14, fontWeight: 600,
  color: colors.ghostText, background: 'transparent',
  border: `1px solid ${colors.ghostBorder}`, cursor: 'pointer', textDecoration: 'none',
}

export const coralDisabled: CSSProperties = {
  background: 'var(--panel-2)', color: 'var(--text-dim)', boxShadow: 'none',
  cursor: 'not-allowed', border: '1px solid var(--border)',
}
