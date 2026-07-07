// web/src/components/SourcePicker.tsx — 분야별 반응형 카드 그리드 + MAX 카운터. v1.1g.
import type { CSSProperties } from 'react'
import type { Category } from '../types'
import { toggleSource } from '../lib/selection'
import { colors } from '../theme'

const SR_ONLY: CSSProperties = {
  position: 'absolute', width: 1, height: 1, padding: 0, margin: -1,
  overflow: 'hidden', clip: 'rect(0 0 0 0)', whiteSpace: 'nowrap', border: 0,
}
const CORAL_GRADIENT = `linear-gradient(135deg, ${colors.coralFrom}, ${colors.coralTo})`

interface Props {
  categories: Category[]
  max: number
  selected: string[]
  onChange: (next: string[]) => void
}

export function SourcePicker({ categories, max, selected, onChange }: Props) {
  const atLimit = selected.length >= max
  return (
    <div>
      <div style={{
        position: 'sticky', top: 0, background: 'var(--bg)', zIndex: 1,
        fontSize: 13, color: atLimit ? colors.coralTo : 'var(--text-dim)',
        fontWeight: atLimit ? 600 : 400, padding: '4px 0', marginBottom: 8,
      }}>
        선택 {selected.length} / {max} (최대 {max}개)
      </div>
      {categories.map((cat) => (
        <fieldset key={cat.name} style={{ border: 'none', padding: 0, margin: '0 0 16px' }}>
          <legend style={{ fontWeight: 600, fontSize: 14, marginBottom: 8, padding: 0 }}>{cat.name}</legend>
          <div className="src-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 10 }}>
            {cat.sources.map((s) => {
              const checked = selected.includes(s.key)
              const dimmed = atLimit && !checked
              const initial = s.name.trim().charAt(0)
              return (
                <div key={s.key} className="src-card" style={cardStyle(checked, dimmed)}>
                  <label className="src-toggle" style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: dimmed ? 'not-allowed' : 'pointer', minWidth: 0 }}>
                    <input
                      type="checkbox"
                      aria-label={s.name}
                      checked={checked}
                      disabled={dimmed}
                      onChange={() => onChange(toggleSource(selected, s.key, max))}
                      style={SR_ONLY}
                    />
                    <span aria-hidden="true" style={avatarStyle(checked)}>{initial}</span>
                    <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0, gap: 2 }}>
                      <span title={s.name} style={{ fontSize: 13, fontWeight: 600, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflowWrap: 'anywhere' }}>{s.name}</span>
                      <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.4, color: 'var(--text-dim)' }}>{s.lang.toUpperCase()}</span>
                    </span>
                  </label>
                  {s.homepage && (
                    <a
                      className="src-host"
                      href={s.homepage}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      style={{ fontSize: 11, color: colors.coralTo, textDecoration: 'none', marginLeft: 42, marginTop: 2 }}
                    >
                      {hostLabel(s.homepage)} <span aria-hidden="true">↗</span>
                    </a>
                  )}
                  {checked && (
                    <span aria-hidden="true" style={{
                      position: 'absolute', top: 6, right: 6, width: 18, height: 18,
                      borderRadius: 9999, background: CORAL_GRADIENT, color: colors.coralInk,
                      fontSize: 11, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>✓</span>
                  )}
                </div>
              )
            })}
          </div>
        </fieldset>
      ))}
    </div>
  )
}

function cardStyle(checked: boolean, dimmed: boolean): CSSProperties {
  return {
    position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'stretch', gap: 4,
    padding: '12px 14px', borderRadius: 12, cursor: dimmed ? 'not-allowed' : 'pointer',
    background: checked ? colors.coralWash : 'var(--panel)',
    border: checked ? `1.5px solid ${colors.coralTo}` : '1px solid var(--border)',
    boxShadow: checked ? '0 1px 10px rgba(255,107,71,0.25)' : undefined,  // 미선택은 인라인 미설정 → hover 시 index.html .src-card:hover 의 코랄 border 로 강조
    opacity: dimmed ? 0.45 : 1,
  }
}

function hostLabel(homepage: string): string {
  try { return new URL(homepage).hostname.replace(/^www\./, '') } catch { return homepage }
}

function avatarStyle(checked: boolean): CSSProperties {
  return {
    flexShrink: 0, width: 32, height: 32, borderRadius: 9999,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 14, fontWeight: 700,
    background: checked ? CORAL_GRADIENT : 'var(--panel-2)',
    color: checked ? colors.coralInk : 'var(--text-dim)',
  }
}
