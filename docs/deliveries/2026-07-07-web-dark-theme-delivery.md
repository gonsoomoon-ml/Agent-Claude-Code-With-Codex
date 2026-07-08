# 웹 다크 테마 전달 기록 (Warm Ink dark theme) — 2026-07-07

**상태: SHIPPED · LIVE** — https://dqizh0gi9cp2q.cloudfront.net · 커밋 `b0b3fa1`

## 무엇을 (What)
④ 웹 UI(랜딩 `/` + 설정 `/setup`) 전 페이지 배경을 **다크(웜 잉크)** 로 전환.
사용자 요청 = "배경을 www.google.com 처럼 다크하게" → 다크(구글 다크홈 계열) 확정.

## 팔레트 (index.html `:root` = single source of truth)
| 토큰 | 값 | 용도 |
|---|---|---|
| `--bg` | `#191410` | 전역 배경(웜 잉크) |
| `--panel` | `#31261c` | 카드·모달·샘플 메일 프레임 (elevation — 2026-07-08 상향) |
| `--panel-2` | `#3a2d20` | 칩(아바타·비활성 버튼) |
| `--border` | `#4d3d2e` | 보더 |
| `--text` | `#efe7de` | 제목·강조 |
| `--text-body` | `#d8cdc0` | 본문(밝게) |
| `--text-dim` | `#b3a596` | 라벨·보조 |
| coral | `#FF9E80→#FF6B47`, ink `#1A0F0A`, wash `rgba(255,107,71,.14)` | CTA·액센트(불변) |

## 결정 (Decisions — 재-litigation 방지)
1. **항상 다크(단일 테마).** 라이트/다크 토글은 **의도적 보류(deferred)** — 팔레트가 `:root` 한 곳에 모여 있어, 나중에 두 번째 팔레트 세트 + 토글만 얹으면 저비용으로 추가 가능.
2. **웜 잉크(중립 근검정 아님) 선택** — 코랄 브랜드 액센트가 이물감 없이 붙도록. 대안 A(구글 뉴트럴 `#131314`)·C(쿨 슬레이트 `#0d1117`)는 **기각(재제안 금지)**.
3. **본문 `#d8cdc0`("밝게")** — 첫 시안의 칙칙한 회색(`#ab9d8d`)을 사용자가 거부 → 상향.
4. **이메일 자체는 라이트 유지** (이메일 클라이언트가 라이트 강제 · 다크메일은 별개의 까다로운 주제). 웹 셸만 다크로 하고, 샘플 메일 iframe 은 "미리보기 · 샘플 메일" **종이/디바이스 프레임**(다크 위 라이트 = 의도된 흰 문서)으로 감쌈.

## 바뀐 파일 (6)
`web/index.html`(토큰 원천 + 전역 스타일) · `web/src/theme.ts` · `pages/Landing.tsx` · `pages/Form.tsx` · `components/SourcePicker.tsx` · `components/ProgressModal.tsx`.
(`App.tsx` 무변경 — `body` 가 배경·기본 글자색 담당하므로 셸은 손댈 필요 없음.)

## 검증 (Verification)
- web 테스트 **33/33** 통과 · `tsc -b && vite build` 클린(타입 에러 0)
- 로컬 preview(프로덕션 카탈로그/샘플 바인딩)로 랜딩·설정 라이브 스크린샷 확인
- 배포 후 **프로덕션 URL 재검증**: 서빙 번들 `index-DyWaiaLv.js` 일치 · `x-cache: Miss`(오리진 신선) · 다크 렌더 확인

## 배포 (Deploy)
`uv run python -m briefing.webapi.deploy_web` — 기존 us-east-1 버킷(`briefing-web-057716757052-us-east-1`) + CloudFront(`E2CUZ0XOLVJ7YL`) **재사용(신규 인프라 없음)** → dist 업로드 → `/*` invalidation.

## 후속 — 소스 카드 elevation (2026-07-08, 커밋 `839a562`)
사용자 지적: 미선택 소스 카드가 배경(`#191410`)에 묻혀 "안 보인다". 원인 = `--panel #241a13` 이 배경과 대비 ~5 L* 뿐.
**다크 UI 는 그림자가 아니라 표면 밝기로 elevation 을 표현** → 카드 채움을 올리는 게 정공법. 4단(현재/잔잔/또렷/강함) 비교 후 **B(또렷)** 채택:
`--panel #241a13→#31261c` (+ 위계 유지 동반 상향 `--panel-2 #2c2119→#3a2d20`·`--border #3d2f22→#4d3d2e`). 같은 토큰을 쓰는 샘플 프레임·인풋도 일관되게 상향; 선택(코랄) 카드 무영향. vitest 33/33·라이브 재검증(index.html `--panel:#31261c` 서빙 확인).

## 후속 — 진행 팝업(체험) 가시성 (2026-07-08, 커밋 `a079c8e`)
문제: `ProgressModal`(체험하기 후 뜨는 팝업)이 카드와 같은 `--panel` 을 써서 "스택 최상단"으로 안 읽힘.
**B안(밝은 표면 + 코랄 보더)** 채택 — 모달을 전용 최상단 elevation 표면으로 승격:
- 신규 토큰: `--elev #3d2f22`(모달 표면) · `--elev-2 #4d3d2e`(닫기 버튼) · `--elev-line #5a4835`(그 보더) · `--coral-line rgba(255,107,71,.65)`(코랄 강조 보더 — 브랜드 액션색, 에러 아님).
- `ProgressModal`: bg `--panel`→`--elev`, border `1px --border`→`1.5px --coral-line`, backdrop `.6`→`.72`, 닫기 버튼 `--elev-2`/`--elev-line`.
- **검증(비자명)**: 실제 모달은 체험하기 클릭 시에만 뜨고 그러면 실 trial 이 발송되므로, **라이브 배포본에서 `window.fetch` 로 `/trial` 요청을 클라이언트에서 가로채(무한 대기 → 실발송 0)** 모달을 busy 상태로 띄워 스크린샷 — 밝은 표면·코랄 보더·진한 백드롭·상향된 닫기 버튼 정상 확인.
