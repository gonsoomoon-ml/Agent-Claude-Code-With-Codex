// web/src/api.ts — API 호출. 빌드 시 VITE_API_BASE(절대 URL); dev 는 ''(Vite 프록시).
export const API_BASE: string = import.meta.env.VITE_API_BASE ?? ''

export async function fetchCatalog(): Promise<import('./types').Catalog> {
  const r = await fetch(`${API_BASE}/catalog`)
  if (!r.ok) throw new Error(`catalog ${r.status}`)
  return r.json()
}

export function sampleUrl(): string {
  return `${API_BASE}/sample`
}
