# docs/ — 실행 산출물 지도 (Execution artifacts map)

> **규칙 3줄:** ① docs/ 루트에는 이 지도만 존재 — 모든 문서는 역할 하위 폴더에 산다. ② `superpowers/` 의 스펙·플랜은 **불변 역사** — 이동·내용 재작성 금지(경로만 깨지면 링크 수선은 허용). ③ 살아남아야 할 결정은 위로 승격한다(truth flows up): CLAUDE.md → 폴더 README → `design/`. 명명: `YYYY-MM-DD-<feature>-….md`.

## 하위 폴더

| 폴더 | 내용 |
|---|---|
| `superpowers/specs/` · `plans/` | 기능별 설계 스펙·구현 플랜 스트림 (아래 색인) |
| `deliveries/` | 배포·검증 전달 기록 |
| `deck/` | 발표자료 작업장 — `make_slide.py`(생성기) · `prd.md`(덱 요구사항) · `*.pptx`(미커밋, 재생성 가능) |
| `assets/` | 스크린샷·이미지 |

## 기능별 색인 (상태: LIVE=프로덕션 가동 · SHIPPED=구현·배포됨 · DRAFT=설계 중 · SUPERSEDED=대체됨)

### web-ui (④ 공개 퍼널) — LIVE (CloudFront dqizh0gi9cp2q)
| 문서 | 상태 |
|---|---|
| specs+plans `2026-06-28-web-ui-design` (v1.0 공개 슬라이스) | SHIPPED·LIVE |
| `…v1.1a-trial` (체험 double-opt-in) | SHIPPED — 쿨다운 규칙은 v1.1e 가 대체 |
| `…v1.1c-trial-progress` · `…v1.1d-progress-modal` | SHIPPED (v1.1c 진행 표시를 v1.1d 모달이 발전) |
| `…v1.1e-trial-cooldown-bypass` (TRIAL_TEST_EMAILS) | SHIPPED |
| `…v1.1f-cta-coral-pill` · `…v1.1g-sourcepicker-card-grid` | SHIPPED |
| `…v1.2-subscribe` (Cognito 가입 + PUT /profile) | SHIPPED — self-signup 차단 결정(2026-07-04): 사용자 생성은 운영자 `admin-create-user` 로만 |
| deliveries `web-ui-v1.0-delivery.md` | v1.0 전달 기록 |

### folder-restructure (저장소 구조 v3) — SHIPPED (2026-07-04 머지+재배포 완료)
| 문서 | 상태 |
|---|---|
| specs `2026-07-03-folder-restructure-design` | SHIPPED — 살아남은 결정은 CLAUDE.md·폴더 README 로 승격됨 |
| plans `2026-07-03-folder-restructure-v3` | SHIPPED (Task 7 재배포 사다리 포함 완료) |

### admin-roles (administrator 역할) — 구현 중
| 문서 | 상태 |
|---|---|
| specs `2026-07-04-admin-roles-design` | DRAFT — Cognito 그룹 + policy seam |
| plans `2026-07-04-admin-roles` | 구현 중 |

> 색인 갱신 시점: 스펙/플랜/전달 기록이 생기거나 상태가 바뀔 때, 해당 커밋에서 함께.
