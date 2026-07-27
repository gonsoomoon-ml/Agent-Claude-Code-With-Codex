# represent-v3.4 독자 관련성 축 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사실층 요약 선택 규칙에 독자 관련성 축을 추가해, 관련성 필터를 통과한 기사의 요약이 원문의 AI 사실을 버리지 않게 한다.

**Architecture:** 변경은 프롬프트 한 곳(`author_system.md` 선택 규칙 말미) + 캐시 버전 상수. 검증은 기존 오프라인 A/B 하네스(`scripts/ab_prompt.py`)에 **신규 지표 1개와 주변부 표본 선택기 1개**를 더해 수행한다. 지연은 A/B(동시 8)가 아니라 `scripts/measure_latency.py`(순차 = 프로덕션 조건)로 따로 잰다.

**Tech Stack:** Python 3.12 · UV · pytest · boto3(DDB 원장/동결본 조회) · `claude -p`(author)

**설계 근거:** `docs/superpowers/specs/2026-07-27-ai-relevance-axis-design.md`

## Global Constraints

- **프레이밍 불변** — 요약의 본 줄기는 기사가 말한 것이고, AI 사실은 *추가*이지 대체가 아니다.
- **없는 사실 생성 금지** — 원문에 AI 관련 서술이 없으면 만들어내지 않는다.
- **길이는 목표가 아니다** — 길이·문장 수는 관측치로만 본다. 길이 계약 3종은 이미 기각된 방향이므로 재도입 금지.
- **지연은 순차로만 판정** — A/B 하네스는 동시 8 실행이라 지연이 부풀려진다. 타임아웃 판단에 쓰지 않는다.
- **회귀 기준 비협상** — 앵커 최심·헤지 보존 하락 시 머지 금지(§Task 3 게이트).
- **프롬프트 재현은 git 원본에서** — 손 surgery 금지(과거 재구성 버그 2건의 교훈).
- **`INTERP_PROMPT_VERSION` 은 올리지 않는다** — `interp_card_key` 가 `fact_key` 를 성분으로 가지므로 `PROMPT_VERSION` 범프만으로 해석층 캐시도 연쇄 무효화된다. 둘 다 올리면 중복이다.
- 문서·docstring·주석은 한국어, 코드 식별자는 영어.

---

### Task 1: A/B 하네스에 AI 사실 포함률 지표 + 주변부 표본 선택기 추가

측정할 자를 프롬프트 변경 **전에** 만든다. 기존 `_sample()` 은 lead bias 순으로 뽑아 이번 질문(주변부 AI 기사)에는 맞지 않는다.

**Files:**
- Modify: `scripts/ab_prompt.py`

**Interfaces:**
- Consumes: `briefing.core.retrieval.relevance` 의 `is_ai_relevant`(동결 키워드 필터), `_EN_RE`, `_FOOTER_RE`, `_KO_KEYWORDS`
- Produces: `_ai_hits(text) -> int` · `_ledger_rows() -> list[tuple[FrozenSource, float, float]]` · `_marginal_sample(n) -> list[tuple[FrozenSource, float, float]]` · `_v33_system() -> str` · 결과 레코드의 `"ai_kept": bool` 필드

- [ ] **Step 1: import 와 지표 헬퍼 추가**

`scripts/ab_prompt.py` 의 import 블록(`from briefing.core.stores.source_store import FrozenSource` 다음 줄)에 추가:

```python
from briefing.core.retrieval.relevance import _EN_RE, _FOOTER_RE, _KO_KEYWORDS, is_ai_relevant
```

`_anchors` 함수 정의 **앞**에 추가:

```python
# ── AI 사실 포함률 (represent-v3.4 게이트 지표) ──────────────────────────────
# 판정은 **동결된 키워드 필터 재사용** — "이 텍스트에 AI 신호가 있나"를 위해 이미 존재하고,
# 동결 상태라 지표가 표류하지 않는다. 절대 정밀도가 아니라 두 팔의 *상대 비교*가 목적.
_MARGINAL_MAX_HITS = 3   # 히트가 이보다 많으면 AI 가 기사의 본 줄기 → 두 팔 다 100% 라 변별력 0


def _ai_hits(text: str) -> int:
    """텍스트의 AI 신호 개수 — 매체 푸터(Powered by …)는 제외(aitimes 푸터 'AI' 오탐 방지)."""
    body = _FOOTER_RE.sub("", text or "")
    return sum(body.count(k) for k in _KO_KEYWORDS) + len(_EN_RE.findall(body))
```

- [ ] **Step 2: `_sample()` 에서 원장 조회부를 분리(DRY)**

기존 `_sample(n)` 전체를 아래 세 함수로 교체한다(원장 조회는 한 곳에만 둔다).

```python
def _ledger_rows() -> list[tuple[FrozenSource, float, float]]:
    """발행 카드 전량 → (동결본, 요약 최심, claims 최심). 표본 선택기들의 공통 원천."""
    ddb = boto3.client("dynamodb", region_name=REGION)
    items, kw = [], {}
    while True:
        r = ddb.query(TableName="briefing-ledger", KeyConditionExpression="user_id = :u",
                      ExpressionAttributeValues={":u": {"S": ADMIN}}, **kw)
        items += [{k: list(v.values())[0] for k, v in it.items()} for it in r["Items"]]
        if "LastEvaluatedKey" not in r:
            break
        kw = {"ExclusiveStartKey": r["LastEvaluatedKey"]}

    rows, seen = [], set()
    for it in items:
        if it["source_id"] in seen:
            continue
        s = ddb.get_item(TableName="briefing-source-store",
                         Key={"source_id": {"S": it["source_id"]}}).get("Item")
        c = ddb.get_item(TableName="briefing-card-cache",
                         Key={"cache_key": {"S": it["card_key"]}}).get("Item")
        if not s or not c or "text" not in s:
            continue
        src = s["text"]["S"]
        if len(src) < 1500:            # 대표할 본문이 있어야 의미
            continue
        seen.add(it["source_id"])
        card = json.loads(c["card_json"]["S"])["card"]
        sd, _ = _depth(src, card.get("summary", ""))
        cd, _ = _depth(src, " ".join(cl["text"] for cl in card.get("claims", [])))
        if sd is None or cd is None:
            continue
        rows.append((FrozenSource(it["source_id"], s.get("url", {}).get("S", ""),
                                  s.get("title", {}).get("S", ""), src, ""), sd, cd))
    return rows


def _sample(n: int) -> list[tuple[FrozenSource, float, float]]:
    """실제 발행 카드 중 **lead bias 가 심했던 것 우선** — 기존 라운드용(동작 불변)."""
    rows = _ledger_rows()
    rows.sort(key=lambda r: r[1] - r[2])   # 요약이 claims 대비 가장 얕은 것부터
    return rows[:n]


def _marginal_sample(n: int) -> list[tuple[FrozenSource, float, float]]:
    """**AI 가 주변부인 기사** 우선 — v3.4 의 변별 표본(안두릴형).

    평범한 AI 기사는 두 팔 모두 AI 사실을 담아 100% 가 나오므로 변별력이 0이다.
    조건: 원문이 관련성 필터를 통과하되(AI 신호 존재) 신호가 희박할 것.
    """
    rows = [r for r in _ledger_rows()
            if is_ai_relevant(r[0].title, r[0].text) and 0 < _ai_hits(r[0].text) <= _MARGINAL_MAX_HITS]
    rows.sort(key=lambda r: _ai_hits(r[0].text))   # 가장 희박한 것부터
    return rows[:n]
```

- [ ] **Step 3: 표본 선택기만 단독 실행해 확인 (author 호출 0회)**

```bash
uv run python -c "
import sys; sys.path.insert(0, 'scripts')
from ab_prompt import _marginal_sample, _ai_hits
rows = _marginal_sample(8)
print(f'주변부 표본 {len(rows)}건')
for fs, sd, cd in rows:
    print(f'  hits={_ai_hits(fs.text):>2}  {fs.title[:56]}')
"
```

Expected: 주변부 기사가 1건 이상 출력된다(안두릴형 = AI 신호 1~3개). **0건이면 중단** — `_MARGINAL_MAX_HITS` 를 5로 올려 재확인하고, 그래도 0이면 원장에 해당 유형이 없다는 뜻이므로 Task 3 의 표본 전략을 사용자와 다시 논의한다.

- [ ] **Step 4: 산출 레코드에 `ai_kept` 추가**

`_run_one` 의 성공 반환 dict 에 필드 하나를 더한다. `"filler": sum(...)` 줄 다음에 추가:

```python
        "ai_kept": is_ai_relevant("", summ),   # v3.4 게이트: 요약이 AI 사실을 담았나
```

- [ ] **Step 5: v3.3 baseline 팔(git 고정) 추가**

`_v3_system()` 정의 다음에 추가. **커밋 고정**이라 워킹트리가 어떻게 변해도 baseline 이 흔들리지 않는다:

```python
_V33_COMMIT = "0284721"   # represent-v3.3 = 독자 관련성 축 추가 직전 (이 스펙의 baseline)


def _v33_system() -> str:
    """v3.3 재현 = git 0284721 의 author_system.md + 현행 lens·계약.

    v3.4 변경은 **md 한정**(선택 규칙에 축 추가)이라 _v3_system 의 summary 줄 surgery 가 필요 없다.
    """
    cur = _current_system()
    return _git_md(_V33_COMMIT) + cur[cur.find("\n\n## 요약 관점(lens)"):]
```

- [ ] **Step 6: 팔 등록·격리 검증·표본 모드 스위치**

`main()` 의 `all_arms` 블록을 교체한다(기존 `"v3.1"` 라벨은 현행이 v3.3 인데도 남아 있던 낡은 이름이다):

```python
    all_arms = {
        "v3": (_v3_system(), _arm_user),
        "v3.3": (_v33_system(), _arm_user),       # baseline (git 0284721 고정)
        "v3.4": (_current_system(), _arm_user),   # 제안 (워킹트리)
    }
```

같은 함수의 `_inv` 딕셔너리를 교체한다:

```python
    _inv = {  # 토큰 → 있어야 하는가
        "v3":   {"3~5문장": False, "위치가 아니라 사실의 무게": True},
        "v3.3": {"독자 관련성 축": False, "위치가 아니라 사실의 무게": True},
        "v3.4": {"독자 관련성 축": True,  "위치가 아니라 사실의 무게": True},
    }
```

`main()` 앞부분의 인자 파싱에 모드를 추가한다. `want = sys.argv[3].split(",") if len(sys.argv) > 3 else None` 다음 줄:

```python
    mode = sys.argv[4] if len(sys.argv) > 4 else "leadbias"   # marginal = v3.4 변별 표본
```

그리고 `sample = _sample(n)` 줄을 교체:

```python
    sample = _marginal_sample(n) if mode == "marginal" else _sample(n)
```

- [ ] **Step 7: 리포트에 지표 출력 추가**

종합 출력 루프에서 `say(f"  filler      : ...")` 줄 **다음**에 추가:

```python
        say(f"  AI 사실 포함 : {sum(1 for r in ok if r.get('ai_kept'))}/{len(ok)}   ← v3.4 게이트 지표")
```

- [ ] **Step 8: 하네스 무결성 확인 (author 호출 0회)**

```bash
uv run ruff check scripts/ab_prompt.py
uv run python -c "
import sys; sys.path.insert(0, 'scripts')
import ab_prompt as ab
a, b = ab._v33_system(), ab._current_system()
print('v3.3 길이', len(a), '· v3.4 길이', len(b))
print('격리: v3.3 에 축 없음 =', '독자 관련성 축' not in a)
print('격리: v3.4 에 축 있음 =', '독자 관련성 축' in b)
"
```

Expected: ruff 통과. 이 시점에는 아직 프롬프트를 안 고쳤으므로 **두 팔이 동일**하고 마지막 줄이 `False` 다 — 정상이다(Task 2 이후 `True` 가 된다).

- [ ] **Step 9: 작업 브랜치 생성 + 커밋**

```bash
git checkout -b feat/represent-v3.4-ai-axis
git add scripts/ab_prompt.py
git commit -m "test(ab): AI 사실 포함률 지표 + 주변부 표본 선택기 + v3.3 baseline 팔

represent-v3.4 게이트용 계측. 판정은 동결 키워드 필터 재사용(표류 방지), 표본은 AI 신호가
희박한 기사(안두릴형)만 — 평범한 AI 기사는 두 팔 다 100% 라 변별력이 없다.
baseline 은 커밋 고정(0284721)이라 워킹트리 변경과 무관하게 재현된다."
```

---

### Task 2: 사실층 선택 규칙에 독자 관련성 축 추가 + 버전 범프

**Files:**
- Modify: `src/briefing/core/prompts/author_system.md` (요약 선택 규칙 절 말미)
- Modify: `src/briefing/core/authoring/author.py` (`PROMPT_VERSION`)
- Test: `tests/test_prompts.py`

**Interfaces:**
- Consumes: `build_system_prompt(lens_guidance=..., skill_md=...)` (기존 시그니처 불변)
- Produces: `PROMPT_VERSION == "represent-v3.4"` — `fact_card_key` 성분이므로 사실층 캐시가 전량 무효화된다

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_prompts.py` 의 `test_prompt_version_matches_contract` 를 아래로 교체하고, 그 **다음**에 새 테스트를 추가한다:

```python
def test_prompt_version_matches_contract():
    """PROMPT_VERSION 은 fact_card_key 성분 — 계약을 바꾸고 안 올리면 구 카드가 새 것인 척 서빙된다."""
    from briefing.core.authoring.author import PROMPT_VERSION

    assert PROMPT_VERSION == "represent-v3.4"


def test_author_system_prompt_has_reader_relevance_axis():
    """독자 관련성 축(v3.4)은 비-오버라이드 규칙 — 지워지면 안두릴형 카드(요약에 AI 0건)가 다시 나온다."""
    from briefing.core.authoring.author import build_system_prompt

    s = build_system_prompt(lens_guidance="", skill_md="")
    assert "독자 관련성 축" in s
    assert "프레이밍은 바꾸지 마라" in s      # (A) 포함이지 (B) 재구성이 아니라는 집행부
```

- [ ] **Step 2: 실패 확인**

```bash
uv run pytest tests/test_prompts.py -k "prompt_version_matches or reader_relevance" -q
```

Expected: 2 failed — `AssertionError: assert 'represent-v3.3' == 'represent-v3.4'` 와 `assert '독자 관련성 축' in s`.

- [ ] **Step 3: 프롬프트 규칙 추가**

`src/briefing/core/prompts/author_system.md` 에서 아래 기존 블록을 찾는다:

```markdown
- 위 넷은 **무엇을 고를지의 기준이지 출력 구조가 아니다.** 라벨·소제목으로 노출하지 마라.
  **축의 순서도 고정이 아니다** — 기사가 요구하는 순서로 쓴다.
```

그 **바로 다음**(다음 `###` 소제목 앞)에 삽입한다:

```markdown
- **독자 관련성 축 (①~④ 와 별개):** 원문에 AI 관련 사실이 있으면 요약은 그것을 담는다.
  이 브리핑의 독자는 AI 를 이유로 구독한다. 기사의 본 줄기가 AI 가 아니어도(예: 방산 기업의
  자금 조달) 원문이 그 기업의 AI 제품·기술·활용을 서술했다면 **한 절(clause) 이상 포함**한다.
  ★ 프레이밍은 바꾸지 마라 — 본 줄기는 여전히 기사가 말한 것이고, AI 사실은 *추가*이지 대체가 아니다.
  **원문에 AI 관련 서술이 없으면 만들어내지 않는다.**
```

- [ ] **Step 4: 버전 상수 갱신**

`src/briefing/core/authoring/author.py` 의 `PROMPT_VERSION` 줄을 교체한다:

```python
PROMPT_VERSION = "represent-v3.4"  # v3.4: 선택 규칙에 독자 관련성 축(AI 사실 포함) 추가
# v3.4 근거(2026-07-27): 관련성 필터를 통과한 기사(안두릴 조달)의 요약에 AI 사실이 0건이었다.
# ①~④ 는 전부 *기사 내부의 무게*만 재고 독자 관련성 축이 없어, 규칙대로 고르면 AI 사실이 탈락한다.
# 포함(A)이지 재구성(B)이 아니다 — 프레이밍을 옮기면 certifier 가 못 잡는 왜곡이 된다.
```

- [ ] **Step 5: 통과 확인 + 전체 스위트**

```bash
uv run pytest tests/test_prompts.py -k "prompt_version_matches or reader_relevance" -q
uv run pytest -q
uv run ruff check src tests
```

Expected: 첫 명령 `2 passed`. 전체 `347 passed, 4 skipped`(기존 346 + 신규 1개 — 버전 트립와이어는 신규가 아니라 *교체*라 수가 늘지 않는다). ruff `All checks passed!`.

- [ ] **Step 6: 커밋**

```bash
git add src/briefing/core/prompts/author_system.md src/briefing/core/authoring/author.py tests/test_prompts.py
git commit -m "feat(prompt): 사실층 요약에 독자 관련성 축 추가 (represent-v3.4)

관련성 필터를 통과한 기사의 요약에 AI 사실이 0건이던 문제(안두릴 카드) 수정.
선택 규칙 ①~④ 는 기사 내부의 무게만 재므로, AI 가 배경인 기사에서 AI 사실이 탈락한다.
①~④ 는 불변으로 두고 별도 축을 추가 — 포함이지 재구성이 아니다(프레이밍 불변 조항).
PROMPT_VERSION 범프로 사실층 캐시 전량 무효화."
```

---

### Task 3: 블라인드 A/B 실행 + 머지 게이트 판정

**Files:**
- 없음(실행·판정만). 산출물은 `$SCRATCH/ab_result.json`

- [ ] **Step 1: 두 팔이 실제로 다른지 확인**

```bash
uv run python -c "
import sys; sys.path.insert(0, 'scripts')
import ab_prompt as ab
a, b = ab._v33_system(), ab._current_system()
assert a != b, 'A/B 무효: 두 팔이 동일'
print('격리 OK · v3.3 에 축 없음 =', '독자 관련성 축' not in a, '· v3.4 에 축 있음 =', '독자 관련성 축' in b)
"
```

Expected: `격리 OK · … True · … True`

- [ ] **Step 2: A/B 실행 (주변부 표본)**

```bash
uv run python scripts/ab_prompt.py 6 3 v3.3,v3.4 marginal
```

6기사 × 2팔 × 3반복 = 36회 author 호출. 수십 분 소요. 진행이 즉시 출력된다.

- [ ] **Step 3: 게이트 판정**

출력 종합 블록을 v3.3 과 v3.4 에 대해 비교한다.

| 지표 | 게이트 |
|---|---|
| **AI 사실 포함** | v3.4 > v3.3 (**상승 필수** — 이게 목적) |
| 요약 최심 median | v3.4 ≥ v3.3 − 노이즈 바닥 (하락 불가) |
| 헤지 보존 | v3.4 ≥ v3.3 (하락 불가) |
| filler | v3.4 ≤ v3.3 (상승 불가) |
| 길이·문장 | **판정에 쓰지 않는다** — 기록만 |

리포트 마지막의 `▸ 노이즈 바닥(같은 기사 반복 간)` 을 반드시 읽는다. 팔 간 차이가 노이즈 바닥보다 작으면 **판정 불가**이며, 그때는 반복(`reps`)을 5로 올려 재실행한다.

**게이트 실패 시:** Task 2 의 커밋을 `git revert` 하고, 실패한 지표와 함께 사용자에게 보고한다. 규칙 문구를 즉흥 수정해 재시도하지 않는다 — 문구 변경은 스펙 개정 사안이다.

- [ ] **Step 4: 결과를 스펙에 기록**

`docs/superpowers/specs/2026-07-27-ai-relevance-axis-design.md` 의 §5 아래에 실측 표를 추가하고 상태 줄을 갱신한다(DRAFT → A/B 통과). 커밋:

```bash
git add docs/superpowers/specs/2026-07-27-ai-relevance-axis-design.md
git commit -m "docs(spec): represent-v3.4 A/B 실측 기록 — 게이트 판정"
```

---

### Task 4: 순차 지연 실측 (타임아웃 위험 판정)

요약이 한 절 늘면 claims 도 늘 수 있고(v3.3 계약: claims = 요약 커버리지), 늘어난 claims 는 author 지연을 360s 천장 쪽으로 민다. A/B 의 초는 동시 8 실행이라 **이 판단에 쓸 수 없다.**

**Files:**
- 없음(실행·판정만)

- [ ] **Step 1: 순차 실측**

```bash
uv run python scripts/measure_latency.py 6
```

- [ ] **Step 2: 판정**

- claims 수 median 이 v3.3 실측(10~22)과 같은 대역인가
- 최대 지연이 `_AUTHOR_TIMEOUT_S`(360s) 대비 여유가 있는가 — v3.3 순차 실측은 119~197s 였다

**여유가 없으면(최대 지연이 300s 초과) 배포하지 않고 보고한다.** 타임아웃 값을 올리는 것은 이 플랜의 범위가 아니다(값 상향은 tail 을 없애지 못한다는 것이 2026-07-18 의 결론).

---

### Task 5: 배포 + 실발송 검증 + 전달 기록

**Files:**
- Create: `docs/deliveries/2026-07-27-ai-relevance-axis-delivery.md`
- Modify: `docs/README.md` (상태 DRAFT → SHIPPED·LIVE)

- [ ] **Step 1: main 머지·푸시**

```bash
git checkout main && git merge --ff-only feat/represent-v3.4-ai-axis && git push origin main
```

- [ ] **Step 2: 런타임 재배포**

```bash
uv run python -m briefing.runtime.deploy_runtime
```

Expected: `Deployment completed successfully` + endpoint READY. **`deploy_scheduler` 는 실행하지 않는다** — 재실행 시 `BRIEFING_DRY_RUN=1` 로 리셋되는 풋건이 있다.

- [ ] **Step 3: trial 실발송으로 확인**

```bash
uv run python -m briefing.runtime.invoke_runtime --mode trial --email <수신주소>
```

받은 메일에서 확인할 것: AI 가 주변부인 기사가 포함됐다면 그 요약에 AI 사실이 한 절 이상 들어갔는가, 그리고 **본 줄기가 여전히 기사의 주제인가**(프레이밍 불변).

- [ ] **Step 4: 전달 기록 작성·커밋**

`docs/deliveries/2026-07-27-ai-relevance-axis-delivery.md` 에 A/B 실측치·순차 지연·배포 ARN·trial 확인 결과를 기록하고, `docs/README.md` 의 `card-content-quality` 스트림에서 스펙 상태를 SHIPPED·LIVE 로 갱신한다.

```bash
git add docs/ && git commit -m "docs(delivery): represent-v3.4 독자 관련성 축 SHIPPED·LIVE"
git push origin main
```

---

## 후속 (이 플랜 밖)

- **해석층 v1.2** — 사실층 배포 후 실제 why 를 보고 필요한 만큼만. 인터프리터는 `verified_claims` 를 앵커로 받으므로 사실층 변경이 하류 재료를 바꾼다. 손잡이(`INTERP_PROMPT_VERSION`)는 이미 구현됨.
- **사실층 summary 의 claim id 무방비** — `author_system.md` 에는 본문 id 인용 금지 규칙이 없다(해석층에만 있음). 관측된 적은 없으나 같은 유형의 구멍.
