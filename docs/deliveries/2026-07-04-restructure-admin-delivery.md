# 2026-07-04 전달 기록 — 폴더 리팩토링 v3 + admin 역할 + 신원 통합 + 웹 프로필 관리

> 하루 동안 4건 출하, 전부 main 머지·origin 푸시·프로덕션 배포·실증 완료. 스펙/플랜 = `docs/superpowers/{specs,plans}/2026-07-03-folder-restructure-*` · `2026-07-04-admin-roles*` · `2026-07-04-web-profile-manage-design`.

## ① 폴더 리팩토링 v3 (`a51fb88..8b7285a`)

- **구조:** `shared/`→`core/`(+`authoring/`(author=claude -p)·`verification/`(certifier=codex exec)로 harness 해체, prompts/·lenses 는 core 루트) · `gateway/` 어댑터 신설(gateway_handler+deploy_gateway) · `runtime/container/`(이미지 빌드 자산 4종) · D6 문서 정리(design/ux/·docs/assets/·docs/deck/) · 폴더 README 7곳.
- **동반 수정(블로커):** `deploy_gateway.py` update 경로에 Handler 푸시 + waiter 추가(없었으면 첫 재배포에서 라이브 Lambda 벽돌) · `test_invariants.py` author↔certifier import 가드에 `verification` 패턴 보강.
- **검증:** pytest 176+3 동수(전 과정) · 라이브 e2e(실 author/certifier 11/11 claim) · 재배포 사다리 완주 — gateway(3도구 byte-identical) → 컨테이너(같은 ARN 재부착 + `mode=scheduled` dry-run으로 lazy 발송 경로 실증) → webapi(전 라우트) → scheduler.
- **운영 함정 발견·복구:** `deploy_scheduler.py` 재실행이 `BRIEFING_DRY_RUN`을 1로 리셋 → 즉시 0 복원. **재배포 후 env 확인 필수.**

## ② admin 역할 v1 (`a39f084..be31ea1`)

- **모델:** Cognito 웹 풀(us-east-1_ANfcEK61A) 그룹 `admins` = 유일한 role 원천(서명된 JWT `cognito:groups` claim; DDB에 role 없음 → mass-assignment 원천 차단). 능력 매핑 = `webapi/policy.py` `max_sources(is_admin)` → 일반 5 / admin `len(CATALOG)`(현재 6).
- **집행:** `app.py` `_parse_groups`(HTTP API v2의 `"[admins]"` 평탄화 문자열·list 양형 수용, fail-closed) → `_claims().is_admin`(기존 401 가드 4중 무변경) → GET /profile 응답 `max_sources` + PUT 검증 kwarg. `profile.py`는 상한 파라미터화(기본 5, 하위호환). **trial·/catalog는 전원 5 고정**(회귀 테스트로 고정). role은 webapi 밖(core/gate/certifier) 무접촉 — opus 보안 리뷰 5/5 PASS.
- **정책 결정:** self-signup **차단 유지**(라이브 상태를 의도로 승격, CFN `AllowAdminCreateUserOnly: true` 정렬 — 드리프트 지뢰 제거). 가입 = 운영자 `admin-create-user`(**`email_verified=true` 필수** — 누락 시 전 API 401; 최종 리뷰 Important).
- **검증:** pytest 176→186(+3 skipped) · vitest 28 · 라이브: 배포된 GET /profile이 비admin에 `max_sources:5`, UI가 5/5에서 6번째 카드 disable, **admin 실계정 6/6 저장 성공**(비교: 일반 6개는 서버 400).

## ③ 신원 통합 — gonsoo→Cognito sub (`2fe9b55` + 운영)

- **문제:** 파일 시대 ID(`gonsoo`)와 Cognito sub(`445814b8-5001-70a6-84a6-6c010ac347ba`)가 같은 사람을 다른 사용자로 취급 → 웹 저장 시 발송 명부 중복(브리핑 2통).
- **이관:** `users/<sub>/skill.md` 복사·커밋(.gitignore 예외) → **컨테이너 재배포로 이미지에 베이크**(skill 오버레이는 `users/<user_id>/` 디렉토리 기준·이미지에 구워짐) → DDB `briefing-users`를 sub 키 단일 항목으로(engineer/full·06:00 KST·6소스 incl. google-research). `users/gonsoo/`는 로컬 개발 예시로 잔존.
- **검증:** override dry-run(`users:[sub]`·`now_utc=21:00Z`·`dry_run:true` — dry는 sent-log 미기록이라 정기 발송 무영향) **658s 완주·카드 경고 0** → 실발송 테스트(`run_date=2026-07-04-test`로 sent-log 키 격리) 20.7s(카드 캐시 재사용)·SES 무반송 · **사용자 수신 확인(Google Research 카드 포함)**.

## ④ 웹 프로필 관리 완성 (`623ce9a..82939e8`)

- **문제:** 폼이 lens='general'·depth='summary'를 하드코딩 → 웹 저장이 기존 engineer/full 스타일을 리셋.
- **구현(web/만, 서버 무변경):** lens·depth 라디오(카탈로그 데이터 기반, 섹션 1미디어·2발송·3관점·4깊이·5이메일) + **구독자 prefill**(GET /profile로 sources/send_hour/lens/depth 채움, 타입 가드) + payload를 state 값으로. 비로그인/실패 시 기본값 폴백.
- **검증:** vitest 30/30 · tsc 클린 · 배포 완료. 이제 admin이 웹에서 저장해도 같은 sub 항목 갱신(중복·스타일 리셋 없음).

## 최종 라이브 상태 (2026-07-04 저녁 실측)

| 설정 | 값 |
|---|---|
| Cognito 풀 | self-signup 차단 · 사용자 1(moongons@amazon.com, CONFIRMED, `admins` 그룹) |
| `briefing-users` | 단일 항목: sub 키 · moongons@amazon.com · 06:00 KST · engineer/full · 6소스 |
| scheduler | `BRIEFING_DRY_RUN=0`(실발송) · `briefing-hourly-tick` ENABLED |
| skill 오버레이 | `users/<sub>/skill.md` 커밋 + 컨테이너 베이크 완료 |
| 테스트 | pytest **186 passed + 3 skipped** · vitest 30 |

## 남은 확인 · 다음 과제

- **07-05 06:00 KST 정기 발송 수신 확인** (새 신원의 첫 자동 발송; silent-failure 통지 미구현이라 능동 확인).
- **다음 1순위: silent-failure 통지** (7/2 인시던트 OPEN — 오늘도 모든 검증이 수동 확인에 의존).
- v-next 소품: `_parse_groups` list-분기 빈 문자열 필터 원라이너 · prefill lens/depth 카탈로그 멤버십 검사 · `/admin/users`·`/admin/resend`(같은 policy seam).
