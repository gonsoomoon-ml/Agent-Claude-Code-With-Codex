# 출처 홈페이지 링크 + Claude Blog 소스 — 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.
> **예외:** Task 4 의 배포 step 은 컨트롤러가 직접 (라이브 웹/Lambda).

**Goal:** `docs/superpowers/specs/2026-07-07-source-homepage-links-design.md` 구현 — (1) `claude-blog` 카탈로그 소스 추가(fetch 스모크 게이트), (2) 카드에 클릭 가능한 홈페이지 링크(호스트명 파생, RSS XML url 미노출, 완전 접근성).

**Architecture:** 서버 `build_catalog`이 소스당 파생 `homepage`(=`https://<hostname>`)를 노출 → 프런트 SourcePicker 카드를 `<div>`+토글 `<label>`+형제 `<a>`로 재구성. Part 1(소스)과 Part 2(링크)는 독립.

**Tech Stack:** Python(FastAPI 카탈로그)·pytest · React/TS(Vite)·vitest.

## Global Constraints (스펙 발췌 — 전 태스크 암묵 적용)

- 서버는 **파생 homepage 만** 노출 — 원 fetch/feed URL(RSS면 `.xml`)은 계속 미노출.
- 링크 클릭은 **선택을 토글하지 않는다**. 토글 영역(아바타+이름) 클릭만 선택.
- `max_sources`·category·정렬·상한 dimmed·✓ 체크마크·admin 등 기존 동작 무변경.
- Part 1 `claude-blog`: fetch 스모크 실패 시 **커밋하지 않는다**. Part 2 는 스모크와 무관하게 진행.
- 표시 라벨은 homepage 에서 `www.` 제거(`www.aitimes.com`→`aitimes.com`); href 는 homepage 원형.
- 커밋 트레일러: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. `users/gonsoo/profile.yaml` 커밋 금지.

---

### Task 1: Part 1 — `claude-blog` 소스 + fetch 스모크 게이트

**Files:**
- Modify: `src/briefing/core/retrieval/catalog.yaml` (항목 1개 추가)

**Interfaces:** Consumes: 없음. Produces: `CATALOG`에 `claude-blog` 소스(html). Part 2 와 독립.

- [ ] **Step 1: 카탈로그 항목 추가** — `catalog.yaml` 끝(마지막 항목 `google-dev` 뒤)에:

```yaml
- key: claude-blog
  name: Claude Blog
  url: https://claude.com/blog
  kind: html
  lang: en
  category: AI·ML 연구·플랫폼
  # 공식 RSS 없음(표준 경로 404) → 리스팅+trafilatura 평문(anthropic 소스 동형, fragile 아님).
  # robots Allow:/ · 제품 아닌 공개 블로그. last-verified: 2026-07-07
```

- [ ] **Step 2: 카탈로그 로드·검증 통과 확인** (import 시 sources.py 가 필수필드·kind 검증):

Run: `uv run python -c "from briefing.core.retrieval.sources import CATALOG; print([s.key for s in CATALOG if s.key=='claude-blog'])"`
Expected: `['claude-blog']` (ValueError 없이 로드)

- [ ] **Step 3: fetch 스모크 (★ 게이트 — 실패 시 중단·롤백)** — 리스팅에서 기사 링크 추출 + trafilatura 본문 추출을 실제로 확인:

```bash
uv run python - <<'PY'
from briefing.core.retrieval.sources import CATALOG, fetch_generic_html
s = next(x for x in CATALOG if x.key == "claude-blog")
arts = fetch_generic_html(s, window_hours=2000)   # 저빈도 블로그 → 넓은 윈도우
print("articles:", len(arts))
for a in arts[:3]:
    print(" -", (a.title or "")[:50], "| body_chars:", len(a.raw_text or ""))
PY
```
Expected: `articles:` ≥ 1, 그리고 상위 기사의 `body_chars` 가 수백 이상(본문 추출 성공). **0건이거나 본문이 비면 게이트 실패** → `git checkout src/briefing/core/retrieval/catalog.yaml`로 롤백하고 컨트롤러에 BLOCKED 보고(claude.com/blog 리스팅 휴리스틱 부적합). Part 2 로 넘어감.

- [ ] **Step 4: 회귀 확인** — `uv run pytest tests/test_webapi_catalog.py tests/test_sources.py -q`
Expected: 전부 PASS (`claude-blog` 포함해 카탈로그 그룹핑·검증 통과).

- [ ] **Step 5: Commit** (스모크 통과 시에만)

```bash
git add src/briefing/core/retrieval/catalog.yaml
git commit -m "feat(catalog): Claude Blog(claude-blog) 출처 추가 — html/trafilatura, fetch 스모크 통과"
```

---

### Task 2: Part 2 서버 — `build_catalog`에 파생 `homepage`

**Files:**
- Modify: `src/briefing/webapi/catalog.py` (`_homepage` 추가 + 소스 dict 확장 + docstring)
- Modify: `tests/test_webapi_catalog.py` (기존 필드-집합 테스트 갱신 + homepage 테스트 추가)

**Interfaces:** Consumes: `Source.url`. Produces: `/catalog` 응답의 각 source dict에 `homepage: str`(= `https://<hostname>`; hostname 없으면 키 생략). Task 3 이 소비.

- [ ] **Step 1: 실패하는 테스트로 교체·추가** — `tests/test_webapi_catalog.py`의 `test_each_source_exposes_key_name_lang_only`를 아래로 **교체**하고, 그 아래 새 테스트 2개 **추가**:

```python
def test_each_source_exposes_expected_fields():
    src = build_catalog()["categories"][0]["sources"][0]
    assert set(src) == {"key", "name", "lang", "homepage"}   # 파생 homepage 노출, 원 url/kind/fragile 은 미노출


def test_homepage_is_derived_host_not_feed_url():
    srcs = {s["key"]: s for g in build_catalog()["categories"] for s in g["sources"]}
    assert srcs["openai"]["homepage"] == "https://openai.com"          # RSS url(…/rss.xml) 아님 — 경로 없음
    assert srcs["anthropic"]["homepage"] == "https://www.anthropic.com"


def test_no_source_leaks_feed_or_xml_url():
    for g in build_catalog()["categories"]:
        for s in g["sources"]:
            assert ".xml" not in s["homepage"] and "/rss" not in s["homepage"] and "/feed" not in s["homepage"]
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_webapi_catalog.py -q`
Expected: 신규 3개 FAIL (`homepage` 키 부재 → KeyError/집합 불일치).

- [ ] **Step 3: 구현** — `catalog.py` 수정. 상단 import 에 `urlparse` 추가하고 `_homepage` 헬퍼 + dict 확장:

```python
from urllib.parse import urlparse   # 파일 상단 import 블록에 추가
```

`build_catalog` 위에 헬퍼 추가:

```python
def _homepage(url: str) -> str | None:
    """fetch/feed URL 에서 사람이 볼 홈페이지 파생 — https://<hostname>. RSS XML 경로는 버린다(호스트만)."""
    host = urlparse(url).hostname
    return f"https://{host}" if host else None
```

`build_catalog` 루프의 append 를 교체 (현재 `groups[cat].append({"key": s.key, "name": s.name, "lang": s.lang})`):

```python
        d = {"key": s.key, "name": s.name, "lang": s.lang}
        hp = _homepage(s.url)
        if hp:
            d["homepage"] = hp
        groups[cat].append(d)
```

파일 docstring(3–4행)의 `url/kind/fragile 은 UI 에 노출하지 않는다.` 를 다음으로 갱신:
`원 url/kind/fragile 은 UI 에 노출하지 않는다 — 단 파생 homepage(https://host)만 노출(XML 엔드포인트 안 샘).`

- [ ] **Step 4: 통과 확인** — `uv run pytest tests/test_webapi_catalog.py -q`
Expected: 전부 PASS.

- [ ] **Step 5: 회귀 + Commit** — `uv run ruff check src tests && uv run pytest -q | tail -1` (기존 + 신규 2개 순증, 동수 green)

```bash
git add src/briefing/webapi/catalog.py tests/test_webapi_catalog.py
git commit -m "feat(webapi): /catalog 에 파생 homepage 노출 (RSS XML url 미노출)"
```

---

### Task 3: Part 2 웹 — 타입 + SourcePicker 카드 재구성

**Files:**
- Modify: `web/src/types.ts` (`SourceItem.homepage?`)
- Modify: `web/src/components/SourcePicker.tsx` (카드 `<label>`→`<div>` + 토글 label + 호스트 링크 + `hostLabel`)
- Modify: `web/src/components/SourcePicker.test.tsx` (`.src-card` 위치 단언 갱신 + 링크 테스트 3개 추가)

**Interfaces:** Consumes: Task 2 의 `homepage`. UI 로직(`toggleSource`·`selection.ts`)은 무변경.

- [ ] **Step 1: 타입 확장** — `web/src/types.ts`의 `SourceItem`:

```ts
export interface SourceItem { key: string; name: string; lang: string; homepage?: string }
```

- [ ] **Step 2: 실패하는 테스트 — 기존 갱신 + 신규 추가** — `web/src/components/SourcePicker.test.tsx`:

기존 3번째 테스트(`renders each source as a card …`) 안의
`const aCard = screen.getByLabelText('A').closest('label')` + `expect(aCard).toHaveClass('src-card')` 두 줄을 아래로 **교체**:

```tsx
    const aCard = screen.getByLabelText('A').closest('.src-card')
    expect(aCard).toBeTruthy()
    expect(aCard?.tagName).toBe('DIV')            // 카드는 이제 div(라벨은 토글 영역만)
```

파일 끝 `describe` 안에 신규 테스트 3개 추가:

```tsx
  const withHost: Category[] = [{ name: '전체', sources: [
    { key: 'a', name: 'A', lang: 'en', homepage: 'https://www.aitimes.com' },
  ] }]

  it('renders a clickable homepage link with www stripped', () => {
    render(<SourcePicker categories={withHost} max={5} selected={[]} onChange={() => {}} />)
    const link = screen.getByRole('link', { name: /aitimes\.com/ })
    expect(link).toHaveAttribute('href', 'https://www.aitimes.com')  // href 는 원형
    expect(link).toHaveAttribute('target', '_blank')
    expect(link.textContent).toContain('aitimes.com')
    expect(link.textContent).not.toContain('www.')                   // 표시는 www 제거
  })

  it('clicking the homepage link does not toggle selection', () => {
    const onChange = vi.fn()
    render(<SourcePicker categories={withHost} max={5} selected={[]} onChange={onChange} />)
    fireEvent.click(screen.getByRole('link', { name: /aitimes\.com/ }))
    expect(onChange).not.toHaveBeenCalled()
  })

  it('renders no link when a source has no homepage', () => {
    render(<SourcePicker categories={cats} max={5} selected={[]} onChange={() => {}} />)
    expect(screen.queryByRole('link')).toBeNull()
  })
```

- [ ] **Step 3: 실패 확인** — `cd web && npm test`
Expected: 신규 3개 + 갱신된 카드 테스트 FAIL (링크 미렌더 / `.src-card` 가 아직 label).

- [ ] **Step 4: 구현** — `web/src/components/SourcePicker.tsx`. (a) `hostLabel` 헬퍼 추가(파일 하단 함수들 근처):

```tsx
function hostLabel(homepage: string): string {
  try { return new URL(homepage).hostname.replace(/^www\./, '') } catch { return homepage }
}
```

(b) 카드 렌더( `cat.sources.map` 안의 `return ( <label …> … </label> )` 전체)를 아래로 교체:

```tsx
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
                      <span style={{ fontSize: 14, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.name}</span>
                      <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.4, color: '#999' }}>{s.lang.toUpperCase()}</span>
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
                      {hostLabel(s.homepage)} ↗
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
```

(c) `cardStyle`을 세로 스택으로 — `display: 'flex'` 뒤 `alignItems: 'center'`를 `flexDirection: 'column', alignItems: 'stretch'`로 변경(아바타+이름 행은 내부 `src-toggle`이 가로 정렬):

```tsx
function cardStyle(checked: boolean, dimmed: boolean): CSSProperties {
  return {
    position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'stretch', gap: 4,
    padding: '12px 14px', borderRadius: 12, cursor: dimmed ? 'not-allowed' : 'pointer',
    background: checked ? colors.coralWash : '#fff',
    border: checked ? `1.5px solid ${colors.coralTo}` : '1px solid #eee',
    boxShadow: checked ? '0 1px 3px rgba(255,107,71,0.18)' : undefined,
    opacity: dimmed ? 0.45 : 1,
  }
}
```

- [ ] **Step 5: 통과 확인** — `cd web && npm test` → 전부 PASS. 그리고 `cd web && npx tsc -b --noEmit` → 타입 클린.

- [ ] **Step 6: Commit**

```bash
git add web/src/types.ts web/src/components/SourcePicker.tsx web/src/components/SourcePicker.test.tsx
git commit -m "feat(web): 소스 카드에 클릭 가능한 홈페이지 링크(호스트명, 접근성 분리)"
```

---

### Task 4: 검증 + 배포 (배포 step 은 컨트롤러 직접)

- [ ] **Step 1: 전체 회귀** — `uv run ruff check src tests` · `uv run pytest -q | tail -1` · `cd web && npm test && npm run build`
Expected: 파이썬 green(동수+신규) · vitest green · 빌드 클린.

- [ ] **Step 2 (컨트롤러): 배포** — `uv run python -m briefing.webapi.deploy_api`(homepage 필드) → `uv run python -m briefing.webapi.deploy_web`(카드). 스모크: `curl $API/catalog | python3 -c "import json,sys; d=json.load(sys.stdin); print([s.get('homepage') for g in d['categories'] for s in g['sources']][:3])"` → `https://…` 값 확인, `.xml` 없음.

- [ ] **Step 3 (컨트롤러): 라이브 확인** — CloudFront 전파 후 설정 페이지에서 카드의 호스트 링크가 새 탭으로 홈페이지를 열고, **링크 클릭이 선택을 토글하지 않는지** 확인. (claude-blog 가 Task 1 에서 커밋됐으면 admin 계정으로 카탈로그에 노출되는지도 확인.)

- [ ] **Step 4: 문서** — `docs/README.md` 색인에 이 기능 SHIPPED 행 추가; 스펙 헤더 상태 갱신. Commit.
