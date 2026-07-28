# interp_audit — 해석층(「사실들을 엮으면」) 오프라인 측정 도구

사실층의 `scripts/ab_prompt.py` 에 대응하는 **해석층 판**이다. 2026-07-28 interp-v1.2 배포의
근거(n=60 · p=0.0000)를 만든 도구 — 전달 기록은 `docs/deliveries/2026-07-28-interp-layer-quality-delivery.md`.

**프로덕션 미접촉:** DDB 는 *읽기만* 하고, 결과는 캐시·원장·발송 어디에도 쓰지 않는다.
`claude -p`(author) 만 실제로 호출한다 — certifier 는 안 돌린다(해석층은 원래 certifier 를 안 거친다).

## 왜 이런 자를 쓰는가 (실패한 자 2종을 먼저 읽어라)

| 자 | 결과 |
|---|---|
| 공허 마무리 정규식 | **실패** — 저장된 why 가 상투구로 끝나는 카드를 재생성해도 0/8. 현상 미재현 |
| (b)/(c) 문체 등급 판정자 | **실패** — 바닥 효과(95건 중 (c) 1건). 강등 사유가 대부분 "자가 대조어 없음"이라 **그 지표에 맞추면 Goodhart** |
| **도출가능성**(`derive_audit.py`) | **작동** — 판정자에게 **요약만** 주고 "이 문단을 요약 독자가 스스로 말할 수 있나". 목표의 정의 그 자체라 게임 불가 |
| 근거(`audit_relation.py` · `score_all.py`) | 작동 — 문단의 주장이 근거 자료로 성립하는가. **팔에 따라 대조 기준이 다르다**(아래 주의) |

두 자를 교차해 2×2 를 만든다:

```
도출가능            → 무의미 (요약이 이미 말한 것)
도출불가 + 근거있음  → 통찰   ← 목표
도출불가 + 근거없음  → 오추론 ← 안전 비용
```

## 파이프라인

```bash
# ① 코퍼스 — 프로덕션 DDB 스캔(읽기 전용). source-store 는 TTL 7일이라 소급 불가 → 감사 전에 떠야 한다.
uv run python scripts/interp_audit/build_dataset.py

# ② 생성 — 팔(arm)별 해석층 산출. 인자 = N 팔 lens (표본은 3버킷: 공허끝·짧은원문·장문)
PILOT_OUT=/tmp/interp-audit/pilot_rows.json \
  uv run python scripts/interp_audit/pilot.py 30 base,beyond engineer,business

# ③ 채점 — 도출가능성 × 근거 → 2×2 + lens 분리 + McNemar 정확검정
uv run python scripts/interp_audit/score_all.py

# ④ 지연 게이트 — **순차(동시성 1) 필수**. 인자 = 팔 N(장문 우선). 배포 가부는 이 숫자로만 판단한다.
uv run python scripts/interp_audit/lat_interp.py base,beyond 6
```

데이터는 `INTERP_AUDIT_DIR`(기본 `/tmp/interp-audit`)에 쌓인다 — 코드만 저장소에 살고
수 MB 짜리 중간 산출물은 밖에 둔다.

## 함정 3개 (전부 실제로 밟았다)

1. **동시 실행 지연을 믿지 마라.** 파일럿은 동시 4로 돌아 초가 부풀려진다. 2026-07-28 아침,
   동시 수치로는 두 팔이 똑같이 타임아웃이라 차이가 묻혔고 — 순차로 재니 **195s 완주 vs 400s 실패**였다.
   장문 기사가 프로덕션에서 통째로 드롭될 뻔했다. 그래서 `lat_interp.py` 가 따로 있다.
2. **표본이 문제를 담고 있어야 한다.** 1차 파일럿은 `claims ≥ 4 + 원문 조인 가능` 으로 걸러
   장문 AWS 문서만 뽑혔고 base 공허끝이 0/6 이었다(전수는 44%). 개선을 잴 수 없다.
   → `load_sample` 이 공허끝/짧은원문/장문 3버킷으로 섞는다.
3. **검정력을 먼저 계산하라.** 15pt 차이 검출에 대응표본 **n=60** 이 필요하다(n=20 은 p=0.125,
   n=40 은 p=0.055). 이보다 작은 실험은 "차이 없음"이 아니라 **"모름"** 이다.

## 팔(arm) 목록과 판정

`pilot.py` 의 `ARMS` — 현행 계약(base)의 `## lens 가 정하는 것` 절 **앞**에 삽입되는 조각들.

| arm | 판정 |
|---|---|
| `base` | 현행(v1.1) 기준선 |
| `struct+sil` · `counterfact` · `conditional` · `relation` · `norepeat` | **전부 기각** — 통찰 4% 정체. 같은 재료로 다르게 쓰라고 시킨 것들이라 한계가 같았다. `conditional` 은 **없는 독자를 발명**했다("당신이 키즈카페 운영 사업자라면") |
| **`beyond`** | **채택 = 배포본(interp-v1.2)** — 요약을 보여주고 "요약이 버린 것"을 쓰게 한다. 통찰 4→36%, p=0.0000 |
| `beyond2` | 기각 — `beyond` + 메타 언급("요약에는 없지만") 금지. 메타 17→0% 는 달성했으나 통찰 35→20%·오추론 0→5%. 그 구절은 상투구가 아니라 **작업 지시의 흔적**이었다 |

★ `score_all.py` 의 근거 대조 기준: `base`·`relation`·`norepeat` 는 **claims** 로, `beyond` 는
**동결 원문**으로 잰다. `beyond` 의 목적이 "요약(=claims 범위)이 버린 것"이라 claims 로 재면 부당하다.

## 승격하지 않은 것

`score2.py`(실패한 M1 문체 판정자 채점기)는 옮기지 않았다 — 그 자 자체가 기각됐다(위 표).
