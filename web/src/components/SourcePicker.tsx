// 분야별 체크박스 + MAX 카운터. category 폴백("전체")도 그대로 렌더.
import type { Category } from '../types'
import { toggleSource } from '../lib/selection'

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
      <div style={{ fontSize: 13, color: '#555', marginBottom: 8 }}>
        선택 {selected.length} / {max} (최대 {max}개)
      </div>
      {categories.map((cat) => (
        <fieldset key={cat.name} style={{ border: '1px solid #eee', borderRadius: 8, marginBottom: 12, padding: '8px 12px' }}>
          <legend style={{ fontWeight: 600, fontSize: 14 }}>{cat.name}</legend>
          {cat.sources.map((s) => {
            const checked = selected.includes(s.key)
            const inputId = `source-${cat.name}-${s.key}`
            return (
              <label key={s.key} htmlFor={inputId} style={{ display: 'block', padding: '4px 0', opacity: !checked && atLimit ? 0.5 : 1 }}>
                <input
                  id={inputId}
                  type="checkbox"
                  checked={checked}
                  disabled={!checked && atLimit}
                  onChange={() => onChange(toggleSource(selected, s.key, max))}
                  aria-label={s.name}
                />{' '}
                {s.name} <span style={{ color: '#999', fontSize: 12 }}>({s.lang})</span>
              </label>
            )
          })}
        </fieldset>
      ))}
    </div>
  )
}
