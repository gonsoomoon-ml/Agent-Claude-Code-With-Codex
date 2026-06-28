// web/src/types.ts — GET /catalog 응답 스키마(api/catalog.py build_catalog 와 1:1).
export interface SourceItem { key: string; name: string; lang: string }
export interface Category { name: string; sources: SourceItem[] }
export interface LensItem { key: string; name: string }
export interface Catalog {
  categories: Category[]
  lenses: LensItem[]
  depths: string[]
  send_hours: number[]
  max_sources: number
}
