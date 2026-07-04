# Administrator 역할 v1 — 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.
> **예외:** Task 6 의 재배포 step 은 컨트롤러가 직접, Task 7(부트스트랩·실계정 인수 테스트)은 **사용자와 함께만** — 서브에이전트 단독 실행 금지.

**Goal:** `docs/superpowers/specs/2026-07-04-admin-roles-design.md` 구현 — Cognito 그룹 `admins` → JWT claim → `webapi/policy.py` seam → 출처 상한(일반 5 / admin 카탈로그 전체=현재 6).

**Architecture:** 판별(claims)·능력(policy)·집행(route) 3분리. role 은 webapi 를 벗어나지 않는다. 서버 검증이 진실, UI 는 `GET /profile` 의 `max_sources` 를 반영만.

**Tech Stack:** FastAPI(+API GW HTTP API JWT authorizer) · pytest(monkeypatch 스타일) · React/vitest.

## Global Constraints (스펙 §4 불변식 — 전 태스크 암묵 적용)

- **role 은 webapi 밖 금지** — core/·gate/·certifier/·scheduler/ 는 이 기능에서 한 글자도 안 바뀐다.
- **`trial.py` 무변경** (전원 5 고정). **`/catalog` 응답의 `max_sources: 5` 무변경** (공개 기본값 — `tests/test_webapi_app.py:15` 단언 유지).
- `PUT /profile` 은 role 관련 어떤 것도 DDB 에 쓰지 않는다. DDB 스키마 무변경.
- `cognito:groups` 파싱은 **list 와 문자열 둘 다** 수용 (HTTP API v2 authorizer 는 배열 claim 을 `"[admins]"` 류 문자열로 평탄화). claim 부재 = is_admin False.
- 테스트 베이스라인 `176 passed, 3 skipped` — 기존 테스트는 전부 무수정 통과(기본값 하위호환), 신규만 추가.
- `users/gonsoo/profile.yaml`(사용자의 uncommitted 수정) 커밋 금지. 커밋 트레일러 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: policy seam — `webapi/policy.py`

**Files:** Create: `src/briefing/webapi/policy.py` · Test: `tests/test_webapi_policy.py`
**Interfaces:** Produces: `max_sources(is_admin: bool) -> int` — Task 3 이 소비.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_webapi_policy.py`:

```python
"""policy — role→능력 매핑 단위 테스트."""
from briefing.core.retrieval.sources import CATALOG
from briefing.webapi.policy import max_sources


def test_general_user_capped_at_5():
    assert max_sources(False) == 5


def test_admin_gets_whole_catalog():
    assert max_sources(True) == len(CATALOG)
    assert max_sources(True) > 0
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_webapi_policy.py -q` → Expected: FAIL `ModuleNotFoundError: briefing.webapi.policy`

- [ ] **Step 3: 구현** — `src/briefing/webapi/policy.py`:

```python
"""policy — role→능력 매핑의 단일 지점 (판별=claims · 능력=여기 · 집행=route 3분리).

향후 관리 능력(사용자 조회·강제 재발송 등)은 이 파일에 함수 하나씩 추가된다.
role 은 webapi 밖으로 나가지 않는다 — core/gate/certifier 는 role 의 존재를 모른다(스펙 §4).
"""
from __future__ import annotations

from ..core.retrieval.sources import CATALOG
from .catalog import MAX_SOURCES


def max_sources(is_admin: bool) -> int:
    """출처 선택 상한. admin 의 '무제한' = 카탈로그 전체 — 실행 시간·비용의 자연 상한."""
    return len(CATALOG) if is_admin else MAX_SOURCES
```

- [ ] **Step 4: 통과 확인** — `uv run pytest tests/test_webapi_policy.py -q` → `2 passed`
- [ ] **Step 5: Commit** — `git add src/briefing/webapi/policy.py tests/test_webapi_policy.py && git commit -m "feat(webapi): policy seam — max_sources(is_admin)"`

---

### Task 2: `validate_profile` 상한 파라미터화

**Files:** Modify: `src/briefing/webapi/profile.py:10-15` · Test: `tests/test_webapi_profile.py` (append)
**Interfaces:** Consumes: 없음. Produces: `validate_profile(..., max_sources: int = 5)` — Task 3 이 소비. 기본값 5 로 기존 8개 테스트 무수정 통과.

- [ ] **Step 1: 실패하는 테스트 추가** — `tests/test_webapi_profile.py` 끝에:

```python
def test_limit_param_allows_six_when_raised():
    kw = dict(KW, catalog_keys=("a", "b", "c", "d", "e", "f"))
    six = {"sources": ["a", "b", "c", "d", "e", "f"], "send_hour": 7}
    assert validate_profile(six, **kw) == "출처를 1~5개 선택하세요."  # 기본 5 유지
    assert validate_profile(six, max_sources=6, **kw) is None


def test_limit_message_reflects_actual_limit():
    kw = dict(KW, catalog_keys=tuple("abcdefg"))
    seven = {"sources": list("abcdefg"), "send_hour": 7}
    assert validate_profile(seven, max_sources=6, **kw) == "출처를 1~6개 선택하세요."
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_webapi_profile.py -q` → Expected: 신규 2개 FAIL (`unexpected keyword argument 'max_sources'`)
- [ ] **Step 3: 구현** — `profile.py:10-15` 를:

```python
# 옛
def validate_profile(fields: dict, *, catalog_keys, lens_keys, depths, send_hours,
                     types: Sequence[str] = ("ai-news",)) -> str | None:
    """6 선호 필드 검증 실패 메시지 or None. recipient/user_id 는 여기서 안 봐(JWT 소유)."""
    sources = fields.get("sources") or []
    if not (1 <= len(sources) <= 5):
        return "출처를 1~5개 선택하세요."
# 새
def validate_profile(fields: dict, *, catalog_keys, lens_keys, depths, send_hours,
                     types: Sequence[str] = ("ai-news",), max_sources: int = 5) -> str | None:
    """6 선호 필드 검증 실패 메시지 or None. recipient/user_id 는 여기서 안 봐(JWT 소유)."""
    sources = fields.get("sources") or []
    if not (1 <= len(sources) <= max_sources):
        return f"출처를 1~{max_sources}개 선택하세요."
```

- [ ] **Step 4: 통과 확인** — `uv run pytest tests/test_webapi_profile.py -q` → 기존 8 + 신규 2 = `10 passed`
- [ ] **Step 5: Commit** — `git commit -m "feat(webapi): validate_profile 상한 파라미터화 (기본 5)"`

---

### Task 3: `app.py` — groups claim → is_admin → 라우트 배선

**Files:** Modify: `src/briefing/webapi/app.py` (import·`_claims`·GET/PUT /profile) · Test: `tests/test_webapi_profile_route.py` (append)
**Interfaces:** Consumes: Task 1 `max_sources`, Task 2 `max_sources=` kwarg. Produces: `_claims()` 반환에 `is_admin: bool` 추가; `GET /profile` 응답에 `max_sources: int` 추가 — Task 4 가 소비.

- [ ] **Step 1: 실패하는 테스트 추가** — `tests/test_webapi_profile_route.py` 끝에 (기존 `_deps`/`_event_from_request` monkeypatch 패턴 그대로; 파일 상단의 기존 `_Store`·`_deps`·client 픽스처 재사용하되, admin 케이스용으로 6-key deps 헬퍼 추가):

```python
def _deps6():
    d = _deps()
    d["keys"] = ["a", "b", "c", "d", "e", "f"]
    return d


def _event_with_groups(groups):
    ev = _event()  # 기존 헬퍼 — claims dict 를 돌려주는 구조에 맞춰 사용
    claims = ev["requestContext"]["authorizer"]["jwt"]["claims"]
    if groups is not None:
        claims["cognito:groups"] = groups
    return ev


def test_parse_groups_accepts_list_and_flattened_string():
    from briefing.webapi.app import _parse_groups
    assert _parse_groups(["admins"]) == {"admins"}
    assert _parse_groups("[admins]") == {"admins"}
    assert _parse_groups("[admins ops]") == {"admins", "ops"}
    assert _parse_groups(None) == set()


def test_get_profile_max_sources_default_5(monkeypatch, client):
    import briefing.webapi.app as appmod
    monkeypatch.setattr(appmod, "_profile_deps", _deps)
    monkeypatch.setattr(appmod, "_event_from_request", lambda req: _event_with_groups(None))
    r = client.get("/profile")
    assert r.status_code == 200 and r.json()["max_sources"] == 5


def test_get_profile_admin_gets_catalog_size(monkeypatch, client):
    import briefing.webapi.app as appmod
    from briefing.core.retrieval.sources import CATALOG
    monkeypatch.setattr(appmod, "_profile_deps", _deps)
    monkeypatch.setattr(appmod, "_event_from_request", lambda req: _event_with_groups("[admins]"))
    r = client.get("/profile")
    assert r.json()["max_sources"] == len(CATALOG)


def test_put_profile_six_sources_rejected_for_general(monkeypatch, client):
    import briefing.webapi.app as appmod
    monkeypatch.setattr(appmod, "_profile_deps", _deps6)
    monkeypatch.setattr(appmod, "_event_from_request", lambda req: _event_with_groups(None))
    r = client.put("/profile", json={"sources": ["a", "b", "c", "d", "e", "f"], "send_hour": 7,
                                     "lens": "general", "depth": "summary"})
    assert r.status_code == 400


def test_put_profile_six_sources_accepted_for_admin(monkeypatch, client):
    import briefing.webapi.app as appmod
    monkeypatch.setattr(appmod, "_profile_deps", _deps6)
    monkeypatch.setattr(appmod, "_event_from_request", lambda req: _event_with_groups(["admins"]))
    r = client.put("/profile", json={"sources": ["a", "b", "c", "d", "e", "f"], "send_hour": 7,
                                     "lens": "general", "depth": "summary"})
    assert r.status_code == 200
```

> 주의: 기존 파일의 `_event()`/`client` 픽스처·`_deps()` 의 실제 이름·shape 에 맞춰 조정하라(파일을 먼저 읽을 것). `_deps()["lenses"]` 에 `"general"` 이 없다면 PUT 테스트의 lens 값을 기존 테스트가 쓰는 값으로 맞춘다. **단언 대상(400/200, max_sources 값)은 불변.**

추가로 **trial 회귀 테스트 1개** (스펙 §6 불변식 5): `tests/test_webapi_trial_route.py` 를 읽고 그 파일의 기존 fake-deps·이벤트 패턴을 재사용해 — **admins 그룹 claim 이 실린 이벤트로 POST /trial 에 소스 6개를 보내면 400** 임을 단언하는 테스트를 그 파일 끝에 추가한다 (trial 은 role 을 조회조차 안 하므로 5 초과는 무조건 거부여야 함). 단언: `r.status_code == 400`.

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_webapi_profile_route.py -q` → 신규 5개 FAIL (`_parse_groups` 부재 / `max_sources` 키 부재)
- [ ] **Step 3: 구현** — `app.py` 세 군데:

① import (기존 `from .profile import validate_profile` 옆):
```python
from .policy import max_sources
```

② `_claims` 위에 헬퍼 추가 + 반환 확장 (`app.py:54-72` 기준):
```python
def _parse_groups(raw) -> set[str]:
    """cognito:groups 정규화 — HTTP API v2 authorizer 는 배열 claim 을 "[a b]" 문자열로 평탄화한다(list·str 둘 다 수용)."""
    if raw is None:
        return set()
    if isinstance(raw, (list, tuple)):
        return {str(g).strip() for g in raw}
    return {g for g in str(raw).strip("[]").replace(",", " ").split() if g}
```
`_claims` 의 마지막 `return {"sub": sub, "email": email}` 을:
```python
    return {"sub": sub, "email": email,
            "is_admin": "admins" in _parse_groups(c.get("cognito:groups"))}
```

③ 라우트 (`app.py:101-121`): GET 의 return 을
```python
    return {"subscribed": rec is not None, "recipient": cl["email"], "profile": rec or {},
            "max_sources": max_sources(cl["is_admin"])}
```
PUT 의 `validate_profile(...)` 호출에 kwarg 추가:
```python
    err = validate_profile(body, catalog_keys=d["keys"], lens_keys=d["lenses"],
                           depths=DEPTHS, send_hours=SEND_HOURS,
                           max_sources=max_sources(cl["is_admin"]))
```

- [ ] **Step 4: 통과 확인** — `uv run pytest tests/test_webapi_profile_route.py tests/test_webapi_app.py -q` → 전부 PASS (catalog 의 `max_sources==5` 단언 포함)
- [ ] **Step 5: 전체 회귀** — `uv run ruff check src tests && uv run pytest -q | tail -1` → `186 passed, 3 skipped` (176 + 신규 10: policy 2 · profile 2 · route 5 · trial 회귀 1)
- [ ] **Step 6: Commit** — `git commit -m "feat(webapi): cognito:groups→is_admin — profile 상한을 policy 로 배선"`

---

### Task 4: 웹 — profile 의 max_sources 반영

**Files:** Modify: `web/src/api.ts:27`, `web/src/pages/Form.tsx` (state·effect·142-144) · Test: `web/src/pages/Form.admin.test.tsx` (신규)
**Interfaces:** Consumes: Task 3 의 `GET /profile.max_sources`. UI 로직 변경 없음 — `SourcePicker`·`selection.ts` 는 이미 max 파라미터화.

- [ ] **Step 1: 실패하는 테스트 작성** — `web/src/pages/Form.admin.test.tsx` (기존 `Form.subscribe.test.tsx` 의 mock 패턴 복제 + max_sources 만 추가):

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Form } from './Form'

vi.mock('../auth/session', () => ({
  isAuthed: () => true, getIdToken: () => 'tok',
  authedFetch: vi.fn(async () => ({ ok: true, json: async () => ({
    subscribed: false, recipient: 'admin@x.com', profile: {}, max_sources: 6 }) })),
}))
vi.mock('../auth/login', () => ({ startLogin: vi.fn() }))

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (u: string) => {
    if (String(u).endsWith('/catalog')) return { ok: true, json: async () => ({
      categories: [{ name: '전체', sources: [
        { key: 'a', name: 'A', lang: 'ko' }, { key: 'b', name: 'B', lang: 'ko' },
        { key: 'c', name: 'C', lang: 'ko' }, { key: 'd', name: 'D', lang: 'ko' },
        { key: 'e', name: 'E', lang: 'ko' }, { key: 'f', name: 'F', lang: 'ko' } ] }],
      lenses: [], depths: [], send_hours: [6, 7, 8], max_sources: 5 }) }
    return { ok: true, json: async () => ({}) }
  }) as unknown as typeof fetch)
})

describe('admin max_sources', () => {
  it('프로필의 max_sources(6)가 헤딩과 카운터에 반영된다', async () => {
    render(<Form />)
    expect(await screen.findByText(/최대 6개/)).toBeInTheDocument()
    expect(screen.getByText(/선택\s*0\s*\/\s*6/)).toBeInTheDocument()
  })
})
```

> 주의: Form 컴포넌트의 export 형태(`export function Form` vs default)와 라우팅 래퍼는 기존 Form 테스트 첫 줄을 그대로 복제해 맞출 것. import 경로·render 방식은 기존 테스트가 진실.

- [ ] **Step 2: 실패 확인** — `cd web && npm test` → 신규 테스트 FAIL (`최대 5개` 렌더)
- [ ] **Step 3: 구현** — ① `api.ts:27` getProfile 반환 타입에 `max_sources?: number` 추가:

```ts
export async function getProfile(): Promise<{ subscribed?: boolean; recipient?: string; delivery?: string; profile?: Record<string, unknown>; max_sources?: number }> {
```

② `Form.tsx` state 블록(:16-22)에 추가:
```tsx
  const [maxSources, setMaxSources] = useState<number | null>(null)
```
③ effect(:42-44) 확장:
```tsx
      getProfile()
        .then((p) => { setRecipient(p.recipient || null); if (p.max_sources) setMaxSources(p.max_sources) })
        .catch((e) => console.error('Failed to get profile:', e))
```
④ 렌더(:142-144) — 실효 상한으로 교체 (비로그인/응답 전 = catalog 기본 5):
```tsx
      const maxSel = maxSources ?? catalog.max_sources   // ← return 문 직전에 선언
      …
      <h2 style={{ fontSize: 16 }}>1. 미디어 선택 <span style={{ color: '#999', fontSize: 13 }}>(최대 {maxSel}개)</span></h2>
      <SourcePicker categories={catalog.categories} max={maxSel} selected={selected} onChange={setSelected} />
```

- [ ] **Step 4: 통과 확인** — `cd web && npm test` → 신규 포함 전부 PASS (기존 테스트의 authedFetch mock 은 max_sources 미포함 → fallback 5 로 무영향)
- [ ] **Step 5: Commit** — `git commit -m "feat(web): profile.max_sources 로 출처 상한 반영 (fallback 5)"`

---

### Task 5: infra 정렬 + 런북 + 문서

**Files:** Modify: `infra/auth/cognito-users.yaml:33`, `infra/README.md`, `src/briefing/webapi/README.md`, `docs/README.md`
**Interfaces:** Consumes: 스펙 §1 결정. 코드 무변경 — pytest 동수 확인만.

- [ ] **Step 1: CFN 선언 정렬** — `cognito-users.yaml:33`:

```yaml
# 옛
        AllowAdminCreateUserOnly: false        # ★ self sign-up 허용(M2M pool 과 반대)
# 새
        AllowAdminCreateUserOnly: true         # ★ 2026-07-04 결정: self-signup 차단 — 가입은 운영자 admin-create-user 로만 (admin-roles 스펙 §1; 라이브 풀과 정렬)
```
스택 업데이트는 **불필요**(라이브가 이미 true — 선언만 정렬).

- [ ] **Step 2: `infra/README.md` 에 런북 절 추가** (표 아래):

```markdown
## 사용자·admin 런북 (Cognito 풀 us-east-1_ANfcEK61A — self-signup 차단)
- 사용자 생성: `aws cognito-idp admin-create-user --user-pool-id us-east-1_ANfcEK61A --username <email>` → 초대 메일(임시 비밀번호) → 첫 로그인 시 hosted UI 가 새 비밀번호 강제
- admin 부여: `aws cognito-idp create-group --group-name admins --user-pool-id us-east-1_ANfcEK61A`(1회) → `aws cognito-idp admin-add-user-to-group --user-pool-id us-east-1_ANfcEK61A --username <sub|email> --group-name admins` → 재로그인(토큰 재발급) 후 적용
- admin 회수: `admin-remove-user-from-group` — 기존 >5 프로필은 발송 유지, 다음 저장부터 5 제한
```

- [ ] **Step 3:** `src/briefing/webapi/README.md` 의 모듈 나열에 `policy.py`(role→능력 매핑 단일 지점 — cognito:groups 는 app.py 가 판별) 한 줄 추가. `docs/README.md` admin-roles 행에 plans 링크 추가(`plans 2026-07-04-admin-roles` · DRAFT→구현 중).
- [ ] **Step 4: 확인 + Commit** — `uv run pytest -q | tail -1`(동수) → `git commit -m "docs+infra: self-signup 차단 선언 정렬 + admin 런북"`

---

### Task 6: 검증 + webapi 재배포 (배포 step 은 컨트롤러 직접)

- [ ] **Step 1:** `uv run ruff check src tests` · `uv run pytest -q | tail -1`(186+3) · `cd web && npm test && npm run build`
- [ ] **Step 2 (컨트롤러):** `uv run python -m briefing.webapi.deploy_api` + `uv run python -m briefing.webapi.deploy_web`(프론트 빌드 반영) → `curl $API/catalog | grep '"max_sources":5'` · 무토큰 `GET /profile → 401`
- [ ] **Step 3:** 커밋 없음 — 검증 게이트.

### Task 7: 부트스트랩 + 인수 테스트 (human-supervised — 사용자와 함께)

- [ ] **Step 1:** 런북 실행 — owner 계정 `admin-create-user`(초대 메일 수신·비밀번호 설정은 사용자) → `create-group` + `admin-add-user-to-group`
- [ ] **Step 2:** 실 로그인 → 설정 화면이 "(최대 6개)" 표시 → **6개 소스 저장 성공** 확인 (DDB `briefing-users` 에 sub 키 아이템 생성됨 — 이 시점부터 해당 계정도 아침 발송 대상이 됨을 사용자에게 고지)
- [ ] **Step 3:** 일반 테스트 계정(그룹 미소속, admin-create-user 로 생성)으로 **6개 저장 400 거부** 확인 → 계정 삭제(`admin-delete-user`)
- [ ] **Step 4:** `docs/README.md` admin-roles 상태 → SHIPPED, 스펙 헤더 DRAFT → SHIPPED. Commit.
