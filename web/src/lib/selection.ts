// 출처 선택 토글(순수). MAX 초과 추가 거부, 선택 해제는 항상 허용.
export function toggleSource(selected: string[], key: string, max: number): string[] {
  if (selected.includes(key)) return selected.filter((k) => k !== key)
  if (selected.length >= max) return selected               // 상한 도달 → 추가 무시
  return [...selected, key]
}
