# 메일 카드 밴드 — 주제(topic) 6칸 묶기 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 메일의 카드 밴드를 발행처(catalog category)에서 기사 단위 주제 6칸으로 바꾸고, 그 분야 라벨을 기존 핵심 3 라벨 호출에 얹어(추가 호출 0) Sonnet 5.5 로 돌린다.

**Architecture:** 공용 분야 상수 `core/areas.py` 를 헤드라인 칸·라벨 프롬프트·render 가 함께 쓴다. `top_picks.py` 의 seam 을 "선택을 돌려주는 함수"에서 **"라벨을 돌려주는 함수"(`LabelFn`)** 로 바꾸고, 핵심 3 선택(`pick_top`)과 분야 맵(`areas_of`)은 코드가 라벨에서 만든다. `render_email` 은 `card_areas` 가 완전할 때만 분야 밴드를 그리고, 아니면 평평 단일 밴드 `요약 N건` — 발행처 밴드 코드는 제거(메일 모양은 둘뿐). 분야는 캐시하지 않는다(run 당 라벨, memo 공유).

**Tech Stack:** Python 3 · boto3 `bedrock-runtime` Converse · pytest · uv · AgentCore Runtime(`deploy_runtime`) · DynamoDB(읽기만: 골든셋 평가)

**Spec:** `docs/superpowers/specs/2026-10-24-topic-grouping-design.md` (§3 결정표 · §4 분야 정의/규칙 · §5 메일 구조 · §6 데이터 흐름 · §7 품질 게이트 · §12 빌더 체크)

## Global Constraints

- 분야 6칸·순서(정본, 영문): `("AI Agents", "Applied AI", "Models & Releases", "Inference & Hardware", "Safety, Security & Policy", "Industry & Business")`. 헤드라인 칸도 같은 목록·순서.
- 메일 모양은 둘뿐: 분야 밴드 / 평평(`◆ 요약 N건` 단일 밴드 또는 핵심 3 없으면 밴드 머리 없음). 발행처 밴드 금지.
- 라벨 호출은 PUBLISH 카드 ≥ `TOP_MIN_CARDS`(6) 일 때만(현행 게이트), 입력 = 보이는 카드 전부(PUBLISH + QUARANTINE), 핵심 3 은 PUBLISH 라벨만. 재시도 정확히 1회. 분야 `area` 는 닫힌 목록 **정확 일치**, 부분 라벨은 채우지 않는다.
- 라벨 입력에 해석층(`why_it_matters`)·사용자 skill 금지(사실층 제목·요약 300자·섹션만). author/certifier/gate/캐시 스키마/`catalog.yaml` 의 category 값 무변경.
- `LABEL_MODEL_ID`(기본 = `RELEVANCE_MODEL_ID`) 는 `.env`·`.env.example`·`deploy_runtime.runtime_env` 세 곳 모두. 관련성 판정 `_converse_text` 는 바이트 동일 유지.
- 모든 로그는 `_debug.warn`(non-silent). 출처 집계 줄 형식 `출처 · {category} {n} · …`(카탈로그 순, 0 생략, 핵심 3·⚠ 포함).
- 문서·docstring·주석은 한국어(식별자·로그는 영어). 각 Task 끝에 `uv run ruff check src tests` 와 `uv run pytest -q` 녹색 뒤 커밋.

## Review Focus

1. 라벨 응답의 `area` 가 대소문자·공백만 다른 경우(`"ai agents"`) → 정확 일치 실패 = 미배정 → 재시도 → 폴백 (Task 3 테스트 `test_parse_labels_area_must_match_closed_list_exactly`).
2. 같은 `n` 이 두 번 오는 응답 → 첫 것만, 나머지 카드 누락이면 불완전 (Task 3 `test_labels_complete_rejects_missing_or_duplicate_n`).
3. 카탈로그 category 가 없는 source_id(테스트 fixture·구 카드) → 출처 집계 줄에서 생략, 크래시 금지 (Task 4 `test_tally_line_omits_unknown_category`).
4. ⚠ 카드가 많아 보이는 카드는 6장 이상인데 PUBLISH 가 6장 미만 → 라벨 호출 없음 → 평평 (Task 3 `test_label_cards_gate_counts_publish_only`).
5. `maxTokens` 절단으로 파싱은 되지만 짧은 배열 → 불완전 → 재시도 (Task 3 `test_llm_labels_retries_once_on_partial_then_raises`).

---

### Task 0: 설계 입력물 커밋 + 작업 브랜치

**Files:**
- Commit(이미 작성됨, 미커밋): `docs/superpowers/specs/2026-10-24-topic-grouping-design.md` · `docs/superpowers/plans/2026-10-24-topic-grouping.md` · `scripts/area_eval/golden_7d.json` · `docs/work_note/Oct-2026/261024-Reorder-Content/classify-7d.md` · `docs/README.md`(색인 1줄)

- [ ] **Step 1: 브랜치** `git checkout -b topic-grouping` (main 에서). `git status --short` 로 위 5개 외 미커밋 변경(`CLAUDE.md` 등 기존 것)은 건드리지 않는다.
- [ ] **Step 2: 커밋**
```bash
git add docs/superpowers/specs/2026-10-24-topic-grouping-design.md docs/superpowers/plans/2026-10-24-topic-grouping.md scripts/area_eval/golden_7d.json docs/work_note/Oct-2026/261024-Reorder-Content/classify-7d.md docs/README.md
git commit -m "docs(topic-grouping): 설계 문서·구현 계획·골든셋 132편·손분류 근거"
```

### Task 1: 공용 분야 상수 `core/areas.py` + 헤드라인 칸 6칸 전환

**Files:**
- Create: `src/briefing/core/areas.py`
- Modify: `src/briefing/core/retrieval/headlines.py:41`(`HEADLINE_AREAS`), `:72-80`(`_AREA_SYSTEM`), `:212-239`(`llm_headline_areas` 의 목록 검사) · `src/briefing/core/render.py:21,195-197`(import·루프)
- Test: `tests/test_areas.py`(신규) · `tests/test_headlines.py:115-157` · `tests/test_render.py:269-283`

**Interfaces:**
- Produces: `areas.AREAS: tuple[str, ...]`(6칸, 메일 순서) · `areas.AREA_DEFINITIONS: str`(라벨 프롬프트용 영문 정의+우선 규칙 — 스펙 §4.1 정의·§4.2 규칙 ①~⑤를 영문으로) · `areas.AREA_DEFINITIONS_HEADLINES: str`(제목 전용 변형 — 스펙 §4.3: 칩·데이터센터 *기술* → Inference & Hardware, *돈* → Industry & Business, 연구 뉴스 → 주제로).
- `headlines.HEADLINE_AREAS` 는 삭제(호환 alias 두지 않음 — grep 로 0 hit 확인).

- [ ] **Step 1: 실패 테스트** `tests/test_areas.py`
```python
from briefing.core import areas
def test_areas_are_the_six_user_approved_names_in_mail_order():
    assert areas.AREAS == ("AI Agents", "Applied AI", "Models & Releases", "Inference & Hardware",
                           "Safety, Security & Policy", "Industry & Business")   # 2026-10-24 사용자 결정
def test_area_definitions_mention_every_area_and_the_five_rules():
    for a in areas.AREAS:
        assert a in areas.AREA_DEFINITIONS and a in areas.AREA_DEFINITIONS_HEADLINES
    assert "availability" in areas.AREA_DEFINITIONS          # 규칙 ② 플랫폼 제공 → Models & Releases
    assert "named" in areas.AREA_DEFINITIONS                 # 규칙 ⑤ named org 사례 → Applied AI
```
- [ ] **Step 2:** `uv run pytest tests/test_areas.py -q` → FAIL(ModuleNotFoundError)
- [ ] **Step 3: 구현** `areas.py` — 상수 3개와 모듈 docstring(왜 공용인지: 한 메일·한 어휘, 스펙 §4). 정의 문장은 스펙 §4.1 표의 "정의" 열을 영문으로 옮기고 규칙 ①~⑤를 번호 목록으로.
- [ ] **Step 4: 헤드라인 테스트 갱신** `tests/test_headlines.py` — `test_headline_areas_are_the_five_user_approved_names_in_order` → `test_headline_areas_use_shared_six_area_list`(`H.AREAS is areas.AREAS` 또는 동등 비교). 라인 121·125·133·141·142 의 `"Research"` → `"Applied AI"`. `tests/test_render.py:271-276` 의 `"Policy & Security"` → `"Safety, Security & Policy"`, `"Research" not in box` → `"Inference & Hardware" not in box`(빈 분야 숨김 단언 유지).
- [ ] **Step 5:** `uv run pytest tests/test_headlines.py tests/test_render.py -q` → 갱신한 테스트 FAIL(아직 5칸)
- [ ] **Step 6: 구현** `headlines.py`: `from ..areas import AREAS, AREA_DEFINITIONS_HEADLINES`; `HEADLINE_AREAS` 삭제; `_AREA_SYSTEM` 을 `AREAS` 와 `AREA_DEFINITIONS_HEADLINES` 로 조립(출력 형식 문장은 유지); `llm_headline_areas` 의 `if area not in HEADLINE_AREAS` → `AREAS`. `render.py`: import 를 `from .areas import AREAS` 로, 루프 2곳 교체. docstring 의 "HEADLINE_AREAS" 언급 갱신.
- [ ] **Step 7:** `grep -rn "HEADLINE_AREAS" src tests` → 0 hit. `uv run pytest -q` → PASS. `uv run ruff check src tests` → clean.
- [ ] **Step 8: 커밋** `git commit -am "feat(areas): 공용 분야 6칸 상수 + 헤드라인 칸 6칸 전환"`

### Task 2: 설정 `LABEL_MODEL_ID` — config · .env · .env.example · runtime_env

**Files:**
- Modify: `src/briefing/core/config.py:60-66`(Settings 꼬리) · `:118-121`(load_settings) · `.env:7` 다음 줄 · `.env.example:23` 다음 줄 · `src/briefing/runtime/deploy_runtime.py:64-66`(조건부 env 묶음)
- Test: `tests/test_config.py` · `tests/test_runtime.py:34-45`

**Interfaces:**
- Produces: `Settings.label_model_id: str = ""`(빈 값 = `relevance_model_id` 상속 — 해석은 호출 시점, `interp_model_id` 와 같은 관례).

- [ ] **Step 1: 실패 테스트** `tests/test_config.py`
```python
def test_label_model_id_defaults_empty_and_reads_env(monkeypatch):
    monkeypatch.delenv("LABEL_MODEL_ID", raising=False)
    assert load_settings().label_model_id == ""
    monkeypatch.setenv("LABEL_MODEL_ID", "global.anthropic.claude-sonnet-5-5")
    assert load_settings().label_model_id == "global.anthropic.claude-sonnet-5-5"
```
`tests/test_runtime.py::test_runtime_env_includes_container_core_keys` 에 추가: `_settings(tmp_path)` 가 `label_model_id` 를 비우면 `"LABEL_MODEL_ID" not in env`; 새 테스트 `test_runtime_env_forwards_label_model_id_when_set` — `_settings(tmp_path, label_model_id="global.anthropic.claude-sonnet-5-5")` → `env["LABEL_MODEL_ID"] == …`(`_settings` 헬퍼에 kwarg 전달 경로가 없으면 `dataclasses.replace` 사용).
- [ ] **Step 2:** 두 테스트 FAIL 확인(TypeError/KeyError).
- [ ] **Step 3: 구현** `Settings.label_model_id: str = ""`(주석: 핵심 3·분야 라벨 호출 모델, 2026-10-24 결정 Sonnet 5.5; 빈 값 = RELEVANCE 상속). `load_settings`: `label_model_id=g("LABEL_MODEL_ID", "").strip()`. `runtime_env`: 조건부 튜플에 `("LABEL_MODEL_ID", settings.label_model_id)` 추가. `.env.example`: `# LABEL_MODEL_ID=global.anthropic.claude-sonnet-5-5  # 핵심 3·분야 라벨 호출 모델(미설정 = RELEVANCE_MODEL_ID). 프로덕션 반영 = deploy_runtime`. `.env`: `LABEL_MODEL_ID=global.anthropic.claude-sonnet-5-5` + 한 줄 주석(2026-10-24 결정, ★ list-inference-profiles 등록 문자열 그대로).
- [ ] **Step 4:** `uv run pytest tests/test_config.py tests/test_runtime.py -q` → PASS(`test_env_example_documents_all_settings_keys` 포함).
- [ ] **Step 5: 커밋** `git commit -am "feat(config): LABEL_MODEL_ID — 핵심 3·분야 라벨 호출 모델(기본 RELEVANCE 상속), runtime env 플럼빙"`

### Task 3: `top_picks.py` — 라벨 seam(`LabelFn`) · `area` 파싱 · 재시도 1회 · `label_cards`/`pick_top`/`areas_of`

**Files:**
- Modify: `src/briefing/core/top_picks.py`(전체 — `TopPickFn`·`llm_top_picks`·`top_source_ids` 를 아래 인터페이스로 교체; `assign_top`·`tier`·`big_org`·`_parse_labels` 유지)
- Test: `tests/test_top_picks.py`

**Interfaces:**
- Produces:
  - `LabelFn = Callable[[Sequence[GatedCard], Sequence[str]], list[dict]]` — (보이는 카드, 카드별 섹션) → **완전한** 라벨 목록(카드마다 `{"n": 0-기반, "org", "type", "importance", "event", "area"}`), 불완전·실패면 **예외**.
  - `class LabelIncomplete(ValueError)` — 사유 문자열 포함(예: `"area 미배정 2/24"`, `"라벨 20/24"`).
  - `labels_complete(labels: list[dict], n_cards: int) -> str` — 빈 문자열이면 완전, 아니면 사유. 조건: `n` 이 0..n_cards-1 각 1회 · `area in AREAS`(정확 일치).
  - `llm_labels(cards, sections, *, invoke) -> list[dict]` — 호출 → `_parse_labels` → `labels_complete`; 예외/불완전이면 **같은 입력으로 1회 재시도**(재시도 사실은 `_debug.dprint` — warn 아님); 그래도 불완전이면 `LabelIncomplete`. 성공 시 warn 없음.
  - `label_cards(cards, label_fn, memo, source_categories: Mapping[str, str]) -> list[dict] | None` — `label_fn is None` 또는 PUBLISH 수 < `TOP_MIN_CARDS` 면 None(호출 없음). 섹션 목록 = `[source_categories.get(g.card.source_id, "") for g in cards]`. memo 키 = `tuple(source_id for 모든 보이는 카드)`. 예외는 warn(`"areas 라벨"`, 사유) 후 None. 성공 시 warn 한 줄 `[WARN areas 라벨] AI Agents 4: 제목…(40자) · … | Applied AI 7: …`(스펙 §6 형식).
  - `pick_top(cards, labels, sections, k=TOP_K) -> tuple[str, ...]` — `labels` 중 `cards[lb["n"]].decision == "PUBLISH"` 만 `assign_top(pub_labels, sections, k)`(섹션 목록은 전체 그대로 — `n` 이 전체 인덱스), 유효 선택 < k 면 warn 후 `()`. 반환 = source_id(표시 순서). 기존 "top picks 선정" warn 로그 유지.
  - `areas_of(cards, labels) -> dict[str, str]` — source_id → area.
  - `_LABEL_SYSTEM` 에 `"area": <exactly one of: …AREAS…>` 필드 + `AREA_DEFINITIONS` 삽입. 기존 `type/org/importance/event` 문장은 **그대로**(스펙 §6 "area 는 추가 필드").

- [ ] **Step 1: 실패 테스트**(기존 `test_llm_top_picks_*`·`test_top_source_ids_*` 3개를 아래로 교체, `_lb` 헬퍼에 `area="AI Agents"` 기본 인자 추가)
```python
def test_parse_labels_area_must_match_closed_list_exactly():
    labs = _parse_labels(json.dumps([{"n": 1, "type": "other", "area": "ai agents"}, {"n": 2, "type": "other", "area": "AI Agents"}]), 2)
    assert labels_complete(labs, 2).startswith("area")            # 대소문자 다른 값 = 미배정(정규화 금지)
def test_labels_complete_rejects_missing_or_duplicate_n():
    assert labels_complete([_lb(0), _lb(0)], 2) and labels_complete([_lb(0)], 2) and labels_complete([_lb(0), _lb(1)], 2) == ""
def test_llm_labels_sends_shown_cards_with_sections_and_area_definitions():
    seen = {}
    def capture(system, user):
        seen["system"], seen["user"] = system, user
        return json.dumps([{"n": i, "type": "other", "importance": 3, "event": f"e{i}", "area": "AI Agents"} for i in range(1, 4)])
    cards = _cards(2) + [_g("q", decision="QUARANTINE")]
    labs = llm_labels(cards, ["Amazon (AWS)", "Google", ""], invoke=capture)
    assert [lb["n"] for lb in labs] == [0, 1, 2] and all(lb["area"] == "AI Agents" for lb in labs)
    assert "3. 제목-q" in seen["user"] and "해석-s1" not in seen["user"]       # ⚠ 포함 · 해석층 제외
    assert "Applied AI" in seen["system"] and '"launch"' in seen["system"]      # 분야 정의 추가, 기존 type 문장 유지
def test_llm_labels_retries_once_on_exception_then_succeeds_quietly(capsys):
    calls = []
    def flaky(s, u):
        calls.append(1)
        if len(calls) == 1: raise RuntimeError("throttled")
        return json.dumps([{"n": 1, "type": "other", "area": "Models & Releases"}])
    assert llm_labels(_cards(1), [""], invoke=flaky)[0]["area"] == "Models & Releases" and len(calls) == 2
    assert "WARN" not in capsys.readouterr().err
def test_llm_labels_retries_once_on_partial_then_raises():
    calls = []
    partial = json.dumps([{"n": 1, "type": "other", "area": "AI Agents"}])      # 2장 중 1장(절단 모양)
    def fn(s, u): calls.append(1); return partial
    with pytest.raises(LabelIncomplete): llm_labels(_cards(2), ["", ""], invoke=fn)
    assert len(calls) == 2                                                     # 정확히 1회 재시도
def test_label_cards_gate_counts_publish_only():
    calls = []
    fn = lambda cards, secs: calls.append(1) or []
    cards = _cards(TOP_MIN_CARDS - 1) + [_g(f"q{i}", decision="QUARANTINE") for i in range(3)]   # 보이는 8장, PUBLISH 5장
    assert label_cards(cards, fn, {}, {}) is None and calls == []
def test_label_cards_memo_by_shown_set_and_failure_is_none_with_warn(capsys):
    calls = []
    def fn(cards, secs):
        calls.append([g.card.source_id for g in cards]); return [_lb(i) for i in range(len(cards))]
    cards = _cards(TOP_MIN_CARDS) + [_g("q", decision="QUARANTINE")]
    memo = {}
    assert label_cards(cards, fn, memo, {"s1": "Anthropic"}) is not None
    assert label_cards(cards, fn, memo, {"s1": "Anthropic"}) is not None and len(calls) == 1 and "q" in calls[0]
    def boom(c, s): raise LabelIncomplete("area 미배정 1/7")
    assert label_cards(cards, boom, {}, {}) is None and "WARN" in capsys.readouterr().err
def test_pick_top_filters_quarantine_in_middle_and_keeps_full_section_indexing():
    cards = [_g("s1"), _g("q", decision="QUARANTINE"), _g("s2"), _g("s3"), _g("s4"), _g("s5"), _g("s6")]
    secs = ["Amazon (AWS)", "News & Media", "Google", "Google", "Community", "Community", "Anthropic"]
    labels = [_lb(0, "AWS", "launch", 5), _lb(1, "OpenAI", "launch", 5), _lb(2, type_="applied", importance=4),
              _lb(3, type_="applied", importance=3), _lb(4, type_="other"), _lb(5, type_="other"), _lb(6, "Anthropic", "launch", 4)]
    assert pick_top(cards, labels, secs) == ("s1", "s6", "s2")    # ⚠(q, OpenAI launch) 제외 · 응용 1장 · 섹션 인덱스 전체 기준
def test_areas_of_maps_every_shown_card():
    cards = _cards(2) + [_g("q", decision="QUARANTINE")]
    assert areas_of(cards, [_lb(0, area="AI Agents"), _lb(1, area="Applied AI"), _lb(2, area="Models & Releases")]) == {
        "s1": "AI Agents", "s2": "Applied AI", "q": "Models & Releases"}
```
- [ ] **Step 2:** `uv run pytest tests/test_top_picks.py -q` → FAIL(ImportError)
- [ ] **Step 3: 구현** 위 인터페이스대로 `top_picks.py` 재구성. 모듈 docstring 에 2026-10-24 결정(라벨 seam·⚠ 포함·재시도 1회·분야 미캐시) 추가. `assign_top`·`_parse_labels` 본문은 유지(`_parse_labels` 는 `area` 를 그대로 통과).
- [ ] **Step 4:** `uv run pytest tests/test_top_picks.py -q` → PASS. (다른 테스트는 Task 5 까지 깨져 있을 수 있음 — 이 Task 는 `tests/test_top_picks.py` 만 녹색이면 커밋.)
- [ ] **Step 5: 커밋** `git commit -am "feat(top_picks): 라벨 seam(LabelFn) + area 닫힌 목록·재시도 1회 + label_cards/pick_top/areas_of"`

### Task 4: `render.py` — `card_areas` 분야 밴드 · 평평 폴백 · 출처 집계 줄 · 발행처 밴드 제거

**Files:**
- Modify: `src/briefing/core/render.py:213-320`(`render_email` 시그니처·밴드 로직·부제 아래 집계 줄) · 모듈 docstring 3번째 줄("분야 = 출처 카탈로그 category") 갱신
- Test: `tests/test_render.py:168-188`(밴드 2종 교체) · `:315-340`(핵심 3 3종 갱신) · 신규 6개

**Interfaces:**
- Produces: `render_email(cards, user, settings, store=None, *, source_categories=None, today=None, headlines=(), top_picks=(), card_areas: Mapping[str, str] | None = None) -> str`. 분기: `card_areas` 가 있고 **보이는 카드 전부**의 area 가 `AREAS` 안이면 분야 밴드(AREAS 순, 빈 칸 숨김, 칸 안 입력 순서 유지, 번호 리셋); 아니면 폴백 = `top` 있으면 `_band("요약", len(rest))` + 전역 번호, 없으면 밴드 머리 없이 평평. `source_categories` 는 집계 줄 전용.
- `_tally_line(shown, cats) -> str` — `출처 · {cat} {n} · …`, 순서 = `src.CATALOG` 의 category 첫 등장 순서(`from .retrieval import sources as src`), 모르는 category 생략, 전부 모르면 빈 문자열(줄 자체 생략). 부제 바로 아래, 부제와 같은 모노 스타일.

- [ ] **Step 1: 실패 테스트**(기존 `test_area_bands_render_when_two_or_more_categories`·`test_no_bands_when_single_category` 삭제 → 아래로; `test_headlines_then_top_picks_then_bands`·`test_top_picks_keep_band_even_when_rest_is_one_category` 는 `card_areas=` 를 넘겨 분야 밴드 이름으로 단언 갱신)
```python
def _areas_for(cards, area="AI Agents"):
    return {g.card.source_id: area for g in cards}
def test_area_bands_follow_shared_order_and_hide_empty():
    cards = [_gated(source_id="a", headline="A"), _gated(source_id="b", headline="B"), _gated(source_id="c", headline="C")]
    out = render_email(cards, _user(), None, card_areas={"a": "Models & Releases", "b": "AI Agents", "c": "Models & Releases"})
    assert out.index("◆ AI Agents") < out.index("◆ Models & Releases") and "◆ Applied AI" not in out
    assert out.index("B") < out.index("A") < out.index("C")                 # 칸 안 입력 순서 유지(정렬 금지)
def test_single_card_band_is_allowed():
    out = render_email([_gated(source_id="a")], _user(), None, card_areas={"a": "Industry & Business"})
    assert "◆ Industry & Business" in out and ">1건<" in out
def test_incomplete_or_missing_card_areas_fall_back_to_one_flat_band():
    cards, cats = _six()
    flat = render_email(cards, _user(), None, source_categories=cats)                           # card_areas 없음(supervisor 경로)
    assert "◆" not in flat                                                   # 핵심 없음 → 밴드 머리 없이 평평(발행처 밴드 없음)
    partial = dict(_areas_for(cards)); partial.pop("c2")
    out = render_email(cards, _user(), None, source_categories=cats, top_picks=["a1"], card_areas=partial)
    assert "◆ 요약 5건" in out and "◆ AI Agents" not in out                                        # 한 장이라도 빠지면 평평
def test_tally_line_counts_shown_cards_in_catalog_order_including_picks():
    cards, cats = _six()
    out = render_email(cards, _user(), None, source_categories=cats, top_picks=["a1"], card_areas=_areas_for(cards))
    assert "출처 · Amazon (AWS) 2 · Google 2 · News & Media 2" in out        # 카탈로그 순(AWS→Google→News), 핵심 포함
def test_tally_line_omits_unknown_category_and_renders_on_fallback():
    cards, cats = _six(); cats = {**cats, "a1": "미상"}
    out = render_email(cards, _user(), None, source_categories=cats)        # 폴백 날에도 집계 줄
    assert "출처 · Amazon (AWS) 2 · Google 2 · News & Media 1" in out and "미상" not in out
def test_subtitle_and_fallback_band_counts_differ_on_purpose():
    cards, cats = _six()
    out = render_email(cards, _user(), None, source_categories=cats, top_picks=["a1", "b1"])
    assert "요약 6건" in out and "◆ 요약 4건" in out                          # 부제 = 전체, 밴드 = 핵심 제외 나머지
```
- [ ] **Step 2:** `uv run pytest tests/test_render.py -q` → FAIL(TypeError: card_areas)
- [ ] **Step 3: 구현** 위 인터페이스. `grouped`/`distinct`/`rest_cats` 발행처 분기 삭제. 주석에 2026-10-24 결정(두 모양·"요약" 어휘·집계 줄 결정론).
- [ ] **Step 4:** `uv run pytest tests/test_render.py -q` → PASS.
- [ ] **Step 5: 커밋** `git commit -am "feat(render): 분야 밴드(card_areas) · 평평 폴백 '요약 N건' · 출처 집계 줄 · 발행처 밴드 제거"`

### Task 5: `pipeline.py` 배선 + pipeline/supervisor 테스트 갱신

**Files:**
- Modify: `src/briefing/core/pipeline.py:31,69,105,142-152`
- Test: `tests/test_pipeline.py:152-206` · `tests/test_supervisor_render.py:19-32`

**Interfaces:**
- Consumes: Task 3 `LabelFn·label_cards·pick_top·areas_of`, Task 4 `render_email(card_areas=)`.
- Produces: `run_briefing(..., label_fn: LabelFn | None = None, ...)` — `top_pick_fn` 인자는 **삭제**(이름 바꾸기, alias 없음). `label_memo: dict[tuple[str, ...], list[dict] | None]`.

- [ ] **Step 1: 테스트 갱신** `tests/test_pipeline.py`: `_top_kw` 유지; `top(cards, k, sections)` fake → 아래 `label(cards, secs)` 로(카드 순서 = 카탈로그 순: claude-blog 3장 → the-decoder 3장이므로 n=0 Anthropic 큰 발표·n=3 OpenAI 큰 발표·n=1 응용 → 핵심 3 = 3장 성립, 나머지 2·4(Applied AI)·5(AI Agents)):
```python
    def label(cards, secs):
        calls.append(len(cards))
        base = [{"n": i, "org": "", "type": "other", "importance": 3, "event": f"e{i}",
                 "area": "AI Agents" if i % 2 else "Applied AI"} for i in range(len(cards))]
        base[0].update(org="Anthropic", type="launch"); base[3].update(org="OpenAI", type="launch"); base[1].update(type="applied")
        return base
```
  단언 `len(calls) == 1 and calls[0] == 6`; 메일 단언 `b.email.index("오늘의 핵심") < b.email.index("◆ AI Agents") < b.email.index("◆ Applied AI")` 와 `"◆ Anthropic" not in b.email`. 문턱 테스트 `boom(_c, _s)` 시그니처로; 실패 테스트 → `raise LabelIncomplete("x")` 로 바꾸고 `"오늘의 핵심" not in email and "◆ 요약 6건" not in email and "◆" not in email`(핵심 없으면 밴드 머리 없음). 신규: `test_run_briefing_label_failure_drops_both_picks_and_bands`(⚠ 1장 섞인 7장, `boom` → 평평·warn). `tests/test_supervisor_render.py::test_render_briefing_passes_area_map_and_date` → 분야 밴드 단언 삭제, `"출처 · " in email` 로(supervisor 는 평평 — 스펙 §12 Q3).
- [ ] **Step 2:** `uv run pytest tests/test_pipeline.py tests/test_supervisor_render.py -q` → FAIL
- [ ] **Step 3: 구현** `pipeline.py`: import 교체, 시그니처 `label_fn`, 루프 안 `labels = label_cards(cards, label_fn, label_memo, source_categories)`; `top = pick_top(cards, labels, [source_categories.get(g.card.source_id, "") for g in cards]) if labels else ()`; `card_areas = areas_of(cards, labels) if labels else None`; `render_email(..., top_picks=top, card_areas=card_areas)`. 주석의 "6장 미만·미주입·실패면 ()" 갱신(실패 = 핵심 3·밴드 동시 상실, 스펙 §6).
- [ ] **Step 4:** `grep -rn "top_pick_fn\|top_source_ids\|llm_top_picks\|TopPickFn" src tests scripts` → **0 hit** (남은 곳은 Task 6 의 runtime 2곳뿐이어야 하며, 그것도 Task 6 에서 0 으로).
- [ ] **Step 5:** `uv run pytest -q` → 전체 PASS(Task 6 의 runtime 테스트 2개 제외 시 실패하면 Task 6 선행 후 재확인). `uv run ruff check src tests` clean.
- [ ] **Step 6: 커밋** `git commit -am "feat(pipeline): label_fn 배선 — 라벨 1회로 핵심 3 + 분야 밴드, ⚠ 포함"`

### Task 6: Bedrock 라벨 헬퍼(Sonnet 5.5) + 런타임 배선 + 스모크(확인 먼저)

**Files:**
- Modify: `src/briefing/core/retrieval/relevance_bedrock.py:14,86-114` · `src/briefing/runtime/agentcore_runtime.py:36-46`
- Test: `tests/test_runtime.py:155-163` · `tests/test_relevance_bedrock.py`(신규 — `_client` monkeypatch 패턴은 `tests/test_relevance.py` 참고)

**Interfaces:**
- Produces: `label_request_fields(model_id: str) -> dict` — 모델별 `additionalModelRequestFields`: `"haiku"` 포함 → `{"thinking": {"type": "disabled"}}`; `"sonnet-5-5"`/`"opus-5-5"` 포함 → **스모크로 확정한 값**(후보 A `{"thinking": {"type": "between_tools"}}`, 후보 B `{}` = adaptive). `LABEL_MAX_TOKENS = 6000`(thinking 켜지면 더). `_converse_label_text(client, model_id, system, user)` — 텍스트 블록 탐색(첫 블록 고정 금지). `make_bedrock_labels(settings) -> LabelFn`(모델 = `settings.label_model_id or settings.relevance_model_id`, 호출마다 warn `[WARN areas 호출] model=…`), `make_bedrock_headline_areas` 도 같은 모델·같은 헬퍼. `_converse_text`(관련성·선별·헤드라인 선별) **무변경**.

- [ ] **Step 1: 실패 테스트** `tests/test_relevance_bedrock.py`
```python
def test_label_request_fields_by_model():
    assert label_request_fields("global.anthropic.claude-haiku-5-5") == {"thinking": {"type": "disabled"}}
    assert "disabled" not in json.dumps(label_request_fields("global.anthropic.claude-sonnet-5-5"))   # Sonnet 5.5: disabled = 400
def test_relevance_helper_still_sends_thinking_disabled(monkeypatch):
    sent = {}
    class C:  # fake bedrock-runtime client
        def converse(self, **kw): sent.update(kw); return {"output": {"message": {"content": [{"text": "YES"}]}}}
    assert _converse_text(C(), "m", "s", "u", 8) == "YES" and sent["additionalModelRequestFields"] == {"thinking": {"type": "disabled"}}
def test_make_bedrock_labels_uses_label_model_and_falls_back_to_relevance(monkeypatch):
    seen = []
    class C:
        def converse(self, **kw): seen.append(kw["modelId"]); return {"output": {"message": {"content": [{"text": "[]"}]}}}
    monkeypatch.setattr(rb, "_client", lambda region: C())
    s = _settings(label_model_id="global.anthropic.claude-sonnet-5-5")        # 이 파일의 로컬 헬퍼(test_runtime._settings 와 같은 모양)
    with pytest.raises(LabelIncomplete): rb.make_bedrock_labels(s)([_g("s1")], [""])
    assert seen == ["global.anthropic.claude-sonnet-5-5"] * 2                      # 재시도 포함 2회, 모델 = LABEL
    seen.clear()
    with pytest.raises(LabelIncomplete): rb.make_bedrock_labels(_settings(label_model_id=""))([_g("s1")], [""])
    assert seen[0] == _settings().relevance_model_id                              # 빈 값 = RELEVANCE 상속
```
`tests/test_runtime.py:161` → `assert "label_fn" in fns`.
- [ ] **Step 2:** FAIL 확인.
- [ ] **Step 3: 구현** 위 인터페이스(후보 A 로 시작). `agentcore_runtime._production_fns`: `fns["label_fn"] = make_bedrock_labels(settings)`; import 갱신; 주석.
- [ ] **Step 4: 스모크(실 호출 1회, 비용 < $0.01)** — 등록 프로필 문자열 확인 후 라벨 헬퍼로 Converse 1콜:
```bash
aws bedrock list-inference-profiles --region us-east-1 --query "inferenceProfileSummaries[?contains(inferenceProfileId,'sonnet-5-5')].inferenceProfileId"
BACKEND=dynamo LABEL_MODEL_ID=global.anthropic.claude-sonnet-5-5 uv run python -c "
from briefing.core.config import load_settings; from briefing.core.retrieval import relevance_bedrock as rb
print(rb._converse_label_text(rb._client('us-east-1'), load_settings().label_model_id, 'Reply with the single word OK.', 'ping')[:40])"
```
기대: `OK` 텍스트, ValidationException 없음. 후보 A 가 400 이면 후보 B 로 바꾸고 `LABEL_MAX_TOKENS` 를 8000 으로 — **어느 후보가 통했는지와 maxTokens 를 `relevance_bedrock.py` 주석과 작업 노트(`docs/work_note/Oct-2026/261024-Reorder-Content/impl-notes.md`)에 기록**.
- [ ] **Step 5:** `grep -rn "top_pick_fn\|make_bedrock_top_pick" src tests scripts` → 0 hit. `uv run pytest -q` 전체 PASS. ruff clean.
- [ ] **Step 6: 커밋** `git commit -am "feat(bedrock): 라벨 호출 헬퍼(LABEL_MODEL_ID·Sonnet 5.5 파라미터) + runtime label_fn 배선"`

### Task 7: 골든셋 평가 러너 + 머지 게이트 실행 (실 호출)

**Files:**
- Create: `scripts/area_eval/run_golden.py` · `scripts/area_eval/headline_check.py` · `scripts/area_eval/README.md`
- Output: `docs/work_note/Oct-2026/261024-Reorder-Content/golden-eval-<YYYYMMDD-HHMM>.md`(+`.json`)

**Interfaces:**
- Consumes: `scripts/area_eval/golden_7d.json`(카드: `headline·summary·category·area·boundary·decision·run_date`), Task 3 `llm_labels·labels_complete·assign_top·tier`, Task 6 `make_bedrock_labels`·`make_bedrock_headline_areas`.
- `run_golden.py --passes 2 [--dry-run]`: run_date 별 묶음(실 호출 크기)으로 `GatedCard` 를 조립(`DraftCard(source_id, headline, summary, "", ())`·verdicts `()`·decision 원본) → 라벨 → 지표: 정확 일치율(분류 가능 고유 카드 131장, `repeat_of_earlier_run` 제외, 1회차), boundary/비경계 불일치 목록(사유 칸 비움), 2회차 일치율, run 별 `pick_top` 결과(10-21~23 는 CloudWatch "top picks 선정" 로그와 나란히 — 관찰). 결과 md+json 을 work_note 에.
- `headline_check.py`: AI타임스 라이브 피드 50제목(`fetch_headline_feed` 재사용) × 2회 `llm_headline_areas` → 미배정 수·2회 일치율·제목별 분야 표.

- [ ] **Step 1: 러너 작성**(테스트는 `--dry-run` 으로 fake invoke 주입 1건: `tests/test_area_eval_runner.py::test_run_golden_metrics_on_fake_labels` — 전부 맞으면 100%, boundary 분해 합이 불일치 수와 같음. 스크립트 import 는 `tests/test_upgrade_eval_*.py` 가 `scripts/upgrade_eval` 을 들여오는 방식을 그대로 따른다).
- [ ] **Step 2: 실행(비용 ≈ $0.5·2회)** `BACKEND=dynamo uv run python scripts/area_eval/run_golden.py --passes 2`. 게이트: **정확 일치 ≥85%**. 미달이면 `areas.AREA_DEFINITIONS` 의 정의·규칙만 고쳐 재실행 — **최대 3회**, 골든 라벨 수정 **≤7장**(사유를 json 에 `golden_fix` 로). 3회 뒤 미달 또는 8장째 수정 필요 → **중단하고 사용자에게**(스펙 §7).
- [ ] **Step 3: 헤드라인 임시 점검** `uv run python scripts/area_eval/headline_check.py` → 미배정 0 · 일치 ≥90% · 50건 손 검토 결과를 같은 work_note 에. 미달이면 `make_bedrock_headline_areas` 만 `relevance_model_id` 로 되돌리는 선택지 기록(이름은 6칸 공용 유지).
- [ ] **Step 4: 핵심 3 관찰** 러너 출력의 10-21~23 선택이 티어 규칙(큰 발표 ≤2·회사당 1·응용 ≥1·섹션당 1)을 만족하는지 손 확인, CloudWatch 와 다른 선택은 사유 한 줄(스펙 §6).
- [ ] **Step 5: 커밋** `git add scripts/area_eval docs/work_note/Oct-2026/261024-Reorder-Content tests/test_area_eval_runner.py && git commit -m "test(area_eval): 골든셋 러너·헤드라인 점검 + 1차 평가 결과"`

### Task 8: 문서 승격 (truth flows up)

**Files:**
- Modify: `design/ux/email-ux-mockup.md:52-57`(§5 "출처 기준" → 주제 6칸·칸 안 카탈로그 순·집계 줄·폴백) · `src/briefing/core/retrieval/catalog.yaml:4-11`(category = picker + 출처 집계·칸 안 순서; 메일 밴드는 주제) · `src/briefing/core/README.md`(해당 절 있으면) · `docs/README.md`(topic-grouping 상태 DRAFT → IMPLEMENTED·미배포, 평가 결과 수치) · `CLAUDE.md`(저장소 현황 한 줄: 카드 밴드 = 주제 6칸)

- [ ] **Step 1:** 위 5곳 갱신. `grep -rn "출처 기준\|분야 = 출처" design src docs/README.md CLAUDE.md` → 남은 서술은 이력 문서(superpowers/·deliveries/)뿐.
- [ ] **Step 2:** `uv run pytest -q` PASS(문서만 바뀌지만 카탈로그 헤더 주석 편집 뒤 로더 확인). 커밋 `git commit -am "docs(topic-grouping): 메일 분야 = 주제 6칸 — 목업 §5·catalog 헤더·README·CLAUDE.md"`.

### Task 9: 배포 (게이트) + 첫 run 검증

**Files:** 없음(운영). 결과 기록: `docs/deliveries/2026-10-XX-topic-grouping-delivery.md`

- [x] **Step 1: 사용자 확인(필수, 기본값 없음)** — "U8 ②(요약 모델 관찰) **앞**에 배포할지 **뒤**에 할지" 답을 받는다. 답 전엔 진행하지 않는다. → **답(2026-10-25): 처음 '뒤' → 같은 날 'deploy' 로 재결정 = 앞(즉시).** 사전 확인 `.env` 요약 모델 Sonnet 5·운영 v59 → ② 미착수라 혼입 없음. Step 2 진행(main `fa72db0`).
- [ ] **Step 2: main 병합** `git checkout main && git merge --no-ff topic-grouping` (사용자가 PR 을 원하면 PR). `uv run pytest -q` 재확인.
- [ ] **Step 3: 배포** `.env` 에 `LABEL_MODEL_ID` 가 있는지 확인 후 `uv run python -m briefing.runtime.deploy_runtime`(런타임 ARN 불변·dry-run 풋건 없음 — `deploy_scheduler` 는 실행 금지). READY 확인.
- [ ] **Step 4: 첫 run 검증(다음 05:00 KST 뒤)** CloudWatch `/aws/bedrock-agentcore/runtimes/briefing_agent-b9uh7rDAqL-DEFAULT` 에서 `"areas 호출"` 줄의 `model=…sonnet-5-5`, `"areas 라벨"` 분포 줄, `"top picks 선정"` 줄; `briefing-sent-log` run_date 의 7명 `status=sent`; 수신 메일에서 출처 집계 줄·6칸 밴드·칸 안 AWS 우선 확인.
- [ ] **Step 5: 전달 기록** deliveries 문서(커밋 해시·runtime 버전·평가 수치·첫 run 관찰) + `docs/README.md` 상태 SHIPPED·LIVE + 메모리 `catalog-publisher-taxonomy`·`project-topic-grouping-redesign` 갱신. 커밋.
