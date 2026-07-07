# 출처 홈페이지 링크 + Claude Blog 소스 — 설계 스펙 (2026-07-07)

> 상태: **SHIPPED** (2026-07-07 배포·라이브 검증) · 관련: `2026-07-04-web-profile-manage-design.md` · 배경: 사용자가 미디어 제목(예: "AI Times")만 보고는 어떤 사이트인지 모른다 → 카드에 클릭 가능한 홈페이지 링크. 겸사겸사 `claude.com/blog`를 카탈로그 소스로 추가.

## Part 1 — `claude-blog` 소스 추가

`src/briefing/core/retrieval/catalog.yaml`에 항목 하나 (기존 `anthropic` html 소스와 동형):

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

**근거(2026-07-07 조사):** robots.txt `Allow:/`(disallow 0). 기사 서버 렌더(`<article>` + 실제 `<p>` 본문, `__NEXT_DATA__` SPA 아님) → trafilatura 추출 가능. 공식 RSS 없음. Consumer Terms의 스크레이핑 금지는 Claude 제품(Services) 대상이지 공개 블로그 아님. anthropic.com/news(회사 발표)와 성격 다름(제품·엔지니어링) → 중복 아닌 보완.

**Acceptance gate(비협상):** 구현 시 실제 fetch 스모크로 리스팅→개별 기사 링크 추출 + 본문 trafilatura 추출을 확인한다. **실패하면 이 항목은 커밋하지 않는다**(HTML 구조 의존이 유일 약점). Part 2 와 독립 — Part 2 는 스모크 결과와 무관하게 진행.

## Part 2 — 카드에 클릭 가능한 홈페이지 링크 (C안)

### 데이터 흐름

카탈로그의 `url`은 **fetch URL**이다 — 9개 중 7개가 RSS면 XML 엔드포인트(`openai.com/news/rss.xml`). 이걸 그대로 링크하면 사용자가 XML을 본다. 따라서 **호스트명에서 파생한 홈페이지**를 노출한다:

```
url(fetch)                          →  homepage(노출)        →  표시 라벨
openai.com/news/rss.xml             →  https://openai.com    →  openai.com
www.aitimes.com/rss/allArticle.xml  →  https://www.aitimes.com →  aitimes.com  (www 제거)
claude.com/blog                     →  https://claude.com    →  claude.com
```

### ① 서버 — `src/briefing/webapi/catalog.py`

`build_catalog`의 소스 dict(현재 `{key, name, lang}`)에 `homepage` 추가:

- `homepage = "https://" + urlparse(s.url).hostname` (hostname 원형 — www 포함 그대로; www 제거는 표시에서만).
- hostname 이 없으면(비정상 url) `homepage` 키 생략 → 프런트가 링크 없이 렌더.
- 파일 docstring의 "url/kind/fragile 은 UI 에 노출하지 않는다"를 갱신: **파생 homepage 만 노출, 원 fetch/feed URL 은 여전히 미노출**(XML 엔드포인트 안 샘).

### ② 타입 — `web/src/types.ts`

`SourceItem`에 `homepage?: string` 추가 (optional — hostname 생략 케이스 대비).

### ③ 카드 — `web/src/components/SourcePicker.tsx` (접근성이 핵심)

현재: `<label>`이 카드 전체를 감싸 어디든 클릭 시 토글. C 는 **토글 영역과 링크를 형제로 분리**:

```
<div class="src-card">                     ← 기존 <label> → <div>, 세로 2단
  <input id={`src-${s.key}`} type=checkbox hidden ...>
  <label htmlFor={`src-${s.key}`} class="src-toggle">   ← 아바타+이름+언어만 감쌈(토글)
     [avatar] [name] [lang]
  </label>
  {s.homepage && (
    <a class="src-host" href={s.homepage} target="_blank" rel="noopener noreferrer"
       onClick={e => e.stopPropagation()}>{hostLabel(s.homepage)} ↗</a>
  )}
  {checked && <span checkmark/>}
</div>
```

- `hostLabel(homepage)` = `new URL(homepage).hostname.replace(/^www\./, "")`.
- 링크는 label 밖 형제 → 중첩 인터랙티브 요소 없음. `stopPropagation`으로 링크 클릭이 토글로 안 번지게(라벨은 htmlFor 연결이라 실제로 형제 클릭은 토글 안 하지만, 방어적으로 유지).
- 카드가 세로로 조금 커짐(이름 줄 + 호스트 링크 줄). 아바타는 좌측, 우측 열에 이름/언어/호스트 링크 스택.
- 선택 시 코럴 스타일·✓ 체크마크·dimmed(상한 도달) 동작은 전부 유지.

### 불변식

- 서버는 파생 homepage 만 노출 — 원 fetch/feed URL 은 계속 미노출.
- 링크 클릭은 **선택을 토글하지 않는다**(별개 동작). 토글 영역 클릭은 기존대로 선택.
- `max_sources`·정렬·category·상한 dimmed·admin 등 기존 동작 무변경.
- Part 1(claude-blog) 과 Part 2(링크)는 독립 — 어느 하나 실패해도 다른 하나는 진행.

## 테스트

- **서버** (`tests/test_webapi_catalog.py` 확장): `build_catalog()["categories"][*]["sources"][*]`에 `homepage` 존재 + `https://`로 시작. RSS 소스(openai 등)의 homepage가 XML url 이 아니라 `https://openai.com` 형태(경로 없음)인지 단언 → XML 미노출 확인.
- **웹** (`SourcePicker.test.tsx` 확장): homepage 있는 소스가 `<a href>`를 렌더하고 라벨이 www 제거형인지; **링크 클릭 시 onChange 가 호출되지 않는지**(stopPropagation); homepage 없는 소스는 링크 미렌더.
- **회귀:** 기존 SourcePicker 테스트(카운터·토글·상한)는 무수정 통과. pytest·vitest 동수+신규.

## 검증 사다리

pytest + vitest + `tsc -b --noEmit` → (Part 1) `claude-blog` fetch 스모크 → `deploy_api`(homepage 필드) + `deploy_web`(카드) → 실 사이트에서 카드 호스트 링크 클릭 시 새 탭 홈페이지 열림 + 선택 토글 안 됨 확인.

## 범위 밖 (YAGNI)

favicon·설명 툴팁·소스별 커스텀 homepage 필드·다국어 라벨. 호스트명 파생으로 충분.
