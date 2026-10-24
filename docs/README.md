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
| deliveries `2026-07-18-summary-quality-certifier-timeout-delivery.md` | **SHIPPED·LIVE**(main ad2a8b1·deploy_runtime READY·deploy_api·trial SES Send=1) — ① certifier 문자열→값 대조(교차언어 위양성 243→6·catch 100%) + 적대 경화 ② SEO 스텁 게이트(MIN_SOURCE_CHARS·openai 비활성) ③ 요약 계약 v3→v3.1(확정)→v3.2(revert)→v3.3(claims=요약 커버리지) ④ author 타임아웃 근본수정(240→360·claims 35→10~22) ⑤ A/B+블라인드 심사 도구. OPEN: (b)잔여 certifier[**2026-07-27 실측**: `arithmetic/DEMOTED` 333건 중 수사(number word) 표현 49건(전체 claim의 0.35%) — 원문이 `the second`·`single-digit` 처럼 **낱말**로 쓴 수량을 값 대조가 못 맞춰 *참인 사실이 `(미확인)` 로 표기*. BLOCKED 아님 = 안전 무손상, 정밀도 손실. **기록만·미조치**: 고치려면 catch-rate 반토막 함정 방향이라 eval_set 확장이 선행]·silent통지·요약예산·독자계측 |

### card-content-quality (발송 카드 내용 품질 — 2026-07-27 실발송 감사에서 발단)
| 문서 | 상태 |
|---|---|
| (스펙 없음 — 직접 수정) 해석층 본문 claim id 유출 | **SHIPPED·LIVE** `c955825`·`deploy_runtime` READY — why 에 "역할 분리(C4, C5)가" 노출. 괄호형=결정론 살균, 인라인=lint 기각→사실층 why 폴백. `INTERP_PROMPT_VERSION` 신설(캐시 히트가 `interpret_card` 를 우회 → 손잡이 없으면 TTL 30일간 구 해석 재서빙). lint 실패 로그 `dprint`→`warn` |
| specs `2026-07-27-ai-relevance-axis-design` · plans `…-ai-relevance-axis` | 설계·플랜(불변 이력). 실제 결과는 delivery 참조 — fat 조항 폐기·lean 확정 등 진화가 있었다 |
| deliveries `2026-07-27-ai-relevance-axis-delivery.md` | **SHIPPED**(main `de81c8f`·`deploy_runtime` READY·ECR `20260727-205949-088`) — 요약 선택 규칙에 독자 관련성 축(represent-v3.4). **배포 근거 = 회귀 없이 특정 실패 유형 해소이지 AI 포함률 전반 개선 아님**(촉발 사례는 독립 2라운드 일관 개선, 전반은 검정력 부족으로 유보). 순차 지연 6/6 완주(max 219s/360s)·헤지·최심·filler 무회귀. ★재제안 금지: fat 조항("둘 다 담는다")은 지표가 훨씬 좋지만(29→75%) 장문 기사를 죽인다(400s·900s 실패) — §5. 잔존: 판정자 배경지식 누출 ~10%(보수적 방향)·gap 모집단 4건. 남은 검증=다음 아침 런 |
| deliveries `2026-07-28-interp-layer-quality-delivery.md` | **SHIPPED·LIVE**(main `1e3a6e5`·`deploy_runtime` READY·ECR `20260728-141922-788`) — 해석층 「나에게 왜 중요한가」→**「사실들을 엮으면」**. 진단: 문체가 아니라 **재료** 문제(도출가능성 92% = 요약만 읽고도 말할 수 있는 것). 해법=요약을 보여주고 "요약이 버린 것"을 쓰게 한다(interp-v1.2). **n=60 McNemar p=0.0000**(통찰 4→36%, 두 lens 각각 유의, 56쌍 중 역전 1). 동반: `based_on` 영속화(`498969c`)·라벨 변경(`09b9b0f`). ★재제안 금지 5종(3칸구조·침묵허가·반사실·**조건부**(없는 독자를 발명)·관계형) 전부 통찰 4% 정체 — §3. ★`(해석)`→`(통찰)` 기각(라벨은 종류, 가치는 독자가 판정) — §6. 계측 승격=`scripts/interp_audit/`. 잔존: 오추론 5% 자동 미감지·빈 why 는 침묵 아닌 폴백 |

### fetch-timeout (수집 페치 시간 상한) — SHIPPED·LIVE (2026-08-10 배포·스모크 검증)
| 문서 | 상태 |
|---|---|
| (스펙 없음 — 인시던트 대응) deliveries `2026-08-10-fetch-timeout-delivery.md` | **SHIPPED·LIVE**(main `f1ce301`·`deploy_runtime` READY v45→v46·ECR `20260810-004316-753`) — 2026-08-09 미발송(**무통보 실패 2번째**). 원인 = trafilatura 가 pycurl 없으면 urllib3 경로, `create_pool(timeout=30)` 은 `Timeout(connect,read)` 이고 **read 는 매 읽기 초기화 = 총 시간 상한 없음**(+backoff 15s). 직렬 파이프라인이라 한 URL 정지 = 브리핑 전체 정지. 수정 = 시간 상한 2층(요청 **20s**/소스 **180s**, `_with_deadline` 를 `_http_get`·`feedparser.parse`·`discover_feed` 에 + 링크 루프 예산; 초과는 `raise` 아닌 `break` = 카드별 격리와 동형). 20s 는 라이브러리 read 30s 보다 **낮아야** 우리가 먼저 이겨 결정론적. ★재제안 금지 4종(`DOWNLOAD_TIMEOUT` 만 축소·`socket.setdefaulttimeout`·소스 병렬화·전역 3층 예산) — §5. **★포렌식 기법 §3**: DDB `ttl` 역산=쓰기 시각(단 source-store 는 `305ed18` TTL 폐지로 이제 불가, card-cache 는 유효)·꼬리 404=소스 통과 마커·**메트릭 flush 는 생존 신호 아님**(오추론 철회 기록). OPEN: silent-failure 통지(증거 2건)·데몬 스레드 잔존·배포가 main 보다 12일 지연이었음 |

### article-identity-dedup (같은 기사 중복 발송 차단) — DRAFT (2026-10-16)
| 문서 | 상태 |
|---|---|
| specs `2026-10-16-article-identity-dedup-design` | **DRAFT** — 감사: 07-08~10-15 8기사·초과 45장. 원인 3층(문서 페이지 오인·본문 해시 신원·7일 lookback) → ① canonical 호스트 검사 ② URL·제목 신원 키 ③ lookback 90일+pagination. DB 스키마·일일 흐름 ASCII 수록. 결정: source-store join + 90일(2026-10-16) |
| plans `2026-10-16-article-identity-dedup` | **DRAFT** — 7 Task(신원 키 → 스토어 get_meta·pagination → 설정 90일 → 파이프라인 → canonical 검사 → 재생 게이트(≤10-15 에서 45장·8기사·AI Times 0) → 출하) |

### claude-codex-upgrade (CLI·모델 업그레이드 + 전후 품질·비용 비교) — 실험 완료·main 병합·단계 배포 중 (2026-10-18)
| 문서 | 상태 |
|---|---|
| specs `2026-10-17-claude-codex-upgrade-design` | **승인·실험 완료(2026-10-17)** — 결과 = 작업 노트 `upgrade-comparison-report.md`(추천: 요약 Sonnet 5.5 + CLI 2.1.301, 검증 GPT-6 Luna + codex 0.163.0). 설계: Stage B(검증 AI: GPT-6 4종 + GPT-5.5 기준선) → Stage A(요약 AI 조건 A0–A5 × 12건 × 3회) → 판정 파이프라인(다섯 질문·결함 심기·사람 20분) → 비용 실측 → 리포트 → 단계 배포. 결정 D1–D6(2026-10-17). 작업 노트 = `docs/work_note/Oct-2026/261016-upgrade-claude-codex/` |
| plans `2026-10-17-claude-codex-upgrade` | **실행 완료(2026-10-17, Native)** — 브랜치 `upgrade-eval` → main 병합(2026-10-18). 13 Task: 작업 공간·프로브 → 공통·codex/author 러너 → 지표 → 기사 선정 → Stage B(+코드 리뷰·재승인 게이트) → Stage A → 판정자·채점(사람 확인 2회) → 비용 → 집계·결정 → 리포트. 배포: F3·F7 배선 + U8 ① CLI 2.1.301 = runtime v54(2026-10-18). 다음 = 아침 발송 관찰 뒤 ② 요약 모델 → F5 → ③ 검증 모델 |

### topic-grouping (메일 카드 밴드 — 발행처 → 주제 6칸) — DRAFT (2026-10-24)
| 문서 | 상태 |
|---|---|
| specs `2026-10-24-topic-grouping-design` | **DRAFT** — 사용자 PRD(`work_note/Oct-2026/261024-Reorder-Content/reorder-prd.md`) → 문제 7건 토론·결정. 밴드 = 기사 단위 주제 6칸(AI Agents → Applied AI → Models & Releases → Inference & Hardware → Safety, Security & Policy → Industry & Business), 핵심 3 라벨 호출에 `area` 추가(추가 호출 0·Sonnet 5.5 `LABEL_MODEL_ID`), 재시도 1회 → 평평 폴백, 출처 집계 줄, 골든셋 132편 ≥85% 머지 게이트. 근거 = `work_note/…/classify-7d.md` + `scripts/area_eval/golden_7d.json`. 다음 = 빌더 체크 → plans |

> 색인 갱신 시점: 스펙/플랜/전달 기록이 생기거나 상태가 바뀔 때, 해당 커밋에서 함께.
