// web/src/theme.ts — v1.1f: 시그니처 코랄 pill CTA 토큰(레퍼런스 차용).
// base look 은 인라인 스프레드, hover/disabled-glyph 는 index.html 의 전역 <style>.
import type { CSSProperties } from 'react'

export const colors = {
  coralFrom: '#FF9E80', coralTo: '#FF6B47', coralInk: '#1A0F0A',
  ghostBorder: 'rgba(0,0,0,0.15)', ghostText: '#444',
  coralWash: 'rgba(255,107,71,0.06)',
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
  background: '#ececec', color: '#aaa', boxShadow: 'none', cursor: 'not-allowed',
}
