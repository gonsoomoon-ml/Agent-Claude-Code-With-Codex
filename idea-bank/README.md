# idea-bank/ — 미검증 아이디어 보관소 (Idea bank)

> 바깥에서 본 것(기사·리포지토리·경쟁 서비스)을 **우리 제약에 비춰 번역해 두는 곳**. 아직 결정이 아니고, 아직 진실도 아니다.

## 왜 `design/` 이 아닌가

`design/` 은 CLAUDE.md 가 정의한 **진실의 원천(source of truth)** 이다. 여기 들어가는 글은 "우리가 무엇을 왜 하기로 했는가"다.
아이디어 뱅크는 그 앞 단계 — **아직 vetting 도, 결정도 안 된 재료**다. 섞으면 `design/` 의 의미가 흐려진다.

## 승격 규칙 (truth flows up)

```
idea-bank/<날짜>-<출처>.md        ← 여기 (미검증 재료·후보·기각 이유)
        ↓  vetting 통과 / 채택 결정
design/research/ · design/architecture/   ← 조사 결과·설계 판단
        ↓  살아남은 결정
CLAUDE.md · 폴더 README            ← 항구적 진실
```

- 채택되면 승격하고, **원본 항목에 승격 링크를 남긴다**(뱅크는 지우지 않는다 — 기각 이유가 재제안을 막는다).
- 기각도 자산이다. **왜 기각했는지**를 반드시 적는다. 이 저장소는 이미 "★재제안 금지" 항목들로 같은 논쟁을 두 번 하지 않는 관례가 있다.

## 채워 넣을 때의 형식

| 절 | 내용 |
|---|---|
| 출처 | 원문 URL + **어떻게 확인했는지**(카드 요약만 읽었는지, 실제 코드를 열었는지) |
| 채널 후보 | 우리 `catalog.yaml` 에 넣을 수 있는 것 — 반드시 vetting 게이트 미통과 상태임을 명시 |
| 아이디어 | 우리 제품에 번역한 형태 + **인클루전 테스트 통과 여부** |
| 기각 | 우리 제약(인클루전 테스트·decorrelation·robots)에 걸린 것과 그 이유 |
| 라이선스 | 코드/데이터를 가져올 여지가 있으면 반드시 |

## 비협상 게이트 (아이디어를 뱅크에서 꺼낼 때 반드시 통과)

1. **인클루전 테스트 3조건**(CLAUDE.md) — 두 하니스가 핵심 / 지속 가능한 고유 상태 / 기본 프리미티브 초과.
2. **소스 추가 vetting**(`design/research/candidate-ai-media-sources.md`) — robots.txt AI 옵트아웃 확인 → `curl` → `fetch_clean_rss` 실추출 → Sponsored 비율 실측 → `MIN_SOURCE_CHARS`(500) 통과.
3. **접근통제 우회 없음** — 발행처가 막으면 막힌 것이다.

## 색인

| 문서 | 출처 | 상태 |
|---|---|---|
| [2026-08-01-world-monitor.md](2026-08-01-world-monitor.md) | World Monitor (OSINT 대시보드, `koala73/worldmonitor`) | 미검증 — 채널 후보 9 · 아이디어 5 · 기각 6 |
</content>
</invoke>
