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

### web-form-two-stage (구독 폼 2단 재구성) — SHIPPED·LIVE (2026-07-08)
| 문서 | 상태 |
|---|---|
| deliveries `2026-07-08-form-two-stage-delivery.md` | SHIPPED·LIVE — `/setup` 을 "① 지금 체험 / ② 매일 구독"으로 분리(예약 시각을 구독 단계로). 프론트 전용. **미해결(deferred): 깊이 full==summary(죽은 옵션) → render+런타임 별건** |

### card-title-original (카드 제목 = 기사 원제목) — SHIPPED·LIVE (2026-07-08)
| 문서 | 상태 |
|---|---|
| deliveries `2026-07-08-card-title-original-delivery.md` | SHIPPED·LIVE — h2=기사 원제목(source.title)·author headline 폐지(PROMPT_VERSION v2·캐시무효화)·출처줄=provenance만. real/lens 재정렬 |

### admin-monitoring (admin 발송 모니터링 대시보드 — Phase 1) — SHIPPED·LIVE (2026-07-09 배포 · 첫 실발송 데이터 확인 대기)
| 문서 | 상태 |
|---|---|
| specs `2026-07-08-admin-monitoring-design` | SHIPPED — PRD `prd_admin.md` Phase 1. 발송 이메일 리스트(기사수·소요시간·발송시각·실비용). 조사: ~$1.10/이메일·9~13분, per-send 감사 레코드 부재 → "계측+UI". role-blind 계측 + `webapi/admin.py` admin-gated 읽기. Deep Insight=Phase 2 북극성 |
| plans `2026-07-08-admin-monitoring` | SHIPPED — 11 태스크 TDD(UsageRecorder→author 봉투비용→gate 배선→pipeline carrier→deliver 반환→sent_log 확장→dispatch audit→admin API→IAM→React /admin). Float→Decimal·authz 추출·certify 추정은 gate.verify_card(certifier 무수정). per-task+opus 최종리뷰 통과·232 py+41 web green |
| deliveries `2026-07-09-admin-monitoring-delivery.md` | SHIPPED·LIVE — 머지 `ee51d6a`(-X theirs, 병렬 card-title/Decoder 통합) + `deploy_api`(sent-log IAM)·`deploy_web`(CloudFront)·`deploy_runtime`(READY) 3종. 배선 확인: `briefing-hourly-tick` ENABLED·dispatch `BRIEFING_DRY_RUN=0`·ARN 일치·`/admin/emails` 401. **첫 실발송 데이터 확인 대기**(백필 불가·dry-run/trial 미기록). footgun: `deploy_scheduler` 금지 |

### summary-quality-certifier-timeout (요약 대표성 + 검증층 + 타임아웃) — SHIPPED·LIVE (2026-07-18 배포·trial 검증)
| 문서 | 상태 |
|---|---|
| specs `2026-07-17-represent-v3-prompt-design` | DRAFT→진화 — 병은 길이가 아니라 lead bias. 실제 결과는 v3.1 확정·v3.2 revert·v3.3(스펙은 불변 이력, 최종은 delivery/메모리) |
| deliveries `2026-07-18-summary-quality-certifier-timeout-delivery.md` | **SHIPPED·LIVE**(main ad2a8b1·deploy_runtime READY·deploy_api·trial SES Send=1) — ① certifier 문자열→값 대조(교차언어 위양성 243→6·catch 100%) + 적대 경화 ② SEO 스텁 게이트(MIN_SOURCE_CHARS·openai 비활성) ③ 요약 계약 v3→v3.1(확정)→v3.2(revert)→v3.3(claims=요약 커버리지) ④ author 타임아웃 근본수정(240→360·claims 35→10~22) ⑤ A/B+블라인드 심사 도구. OPEN: (b)잔여 certifier·silent통지·요약예산·독자계측 |

> 색인 갱신 시점: 스펙/플랜/전달 기록이 생기거나 상태가 바뀔 때, 해당 커밋에서 함께.
