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

### admin-roles (administrator 역할) — SHIPPED (2026-07-04 배포·실계정 인수 완료)
| 문서 | 상태 |
|---|---|
| specs `2026-07-04-admin-roles-design` | SHIPPED — Cognito 그룹(admins) + webapi policy seam |
| plans `2026-07-04-admin-roles` | SHIPPED — Task 7 인수: admin 계정 6/6 저장 성공, 비admin 5 상한 라이브 확인 |

### web-profile-manage (웹 프로필 관리 완성) — SHIPPED (2026-07-04)
| 문서 | 상태 |
|---|---|
| specs `2026-07-04-web-profile-manage-design` | SHIPPED — lens·depth 라디오 + 구독자 prefill(하드코딩 제거); gonsoo→admin(sub) 신원 이관·skill 오버레이 베이크·dry-run 검증 동반 |
| deliveries `2026-07-04-restructure-admin-delivery.md` | 하루 전달 기록 — 리팩토링 v3 + admin + 신원 통합 + 웹 관리 (검증 증거·최종 라이브 상태 포함) |

### source-homepage-links (출처 홈페이지 링크 + Claude Blog) — SHIPPED (2026-07-07)
| 문서 | 상태 |
|---|---|
| specs `2026-07-07-source-homepage-links-design` | SHIPPED — 카드에 클릭 가능 홈페이지 링크(호스트명 파생, RSS XML 미노출) + `claude-blog` 소스 |
| plans `2026-07-07-source-homepage-links` | SHIPPED — 배포·라이브 검증(링크 새 탭·클릭 토글 안 함, claude-blog 노출) |

### web-dark-theme (웹 다크 테마 — 웜 잉크) — SHIPPED·LIVE (2026-07-07)
| 문서 | 상태 |
|---|---|
| deliveries `2026-07-07-web-dark-theme-delivery.md` | SHIPPED·LIVE — 전 페이지 다크(웜 잉크 `#191410`) + `:root` 토큰 단일화. 결정: 토글 보류(deferred)·이메일 라이트 유지(프레이밍)·대안 뉴트럴/슬레이트 기각 |

### catalog-publisher-taxonomy (소스 분류 발행처 재편 + AWS KR 블로그) — SHIPPED·LIVE (2026-07-08)
| 문서 | 상태 |
|---|---|
| deliveries `2026-07-08-catalog-publisher-taxonomy-delivery.md` | SHIPPED·LIVE — 섹션을 발행처 기준으로(뉴스·미디어·AWS·Anthropic·OpenAI·Google) + AWS Korea Tech Blog(ko) 추가. API+런타임 재배포(스케줄러 ARN 불변·dry-run 보존). category=웹+이메일 공통 키 |

> 색인 갱신 시점: 스펙/플랜/전달 기록이 생기거나 상태가 바뀔 때, 해당 커밋에서 함께.
