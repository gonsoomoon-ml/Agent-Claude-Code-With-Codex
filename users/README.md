# users/ — per-user 설정 (다중 사용자, design-for-N)

`users/<id>/` 하나 = 사용자 1명:
- `profile.yaml` — 운영(recipient·type·sources·depth·lens·send_hour·timezone). `config.load_user()` 가 읽음.
- `skill.md` — 편집 개인화(역할·토픽·보이스). author 에 `--append-system-prompt` 로 주입(★ certifier 미열람).

## ⚠️ PII — 무엇을 커밋하나
`recipient`(이메일)·프로필은 **PII**. `.gitignore` 가 `users/*` 를 무시하되 **`users/gonsoo/`(개발자 본인 예시)만 커밋**한다.
- 로컬 테스트로 실제 사용자(`users/alice/` 등)를 추가해도 *자동으로 커밋 안 됨*.
- 실제 다중 사용자(웹-UI)는 파일이 아니라 **DB**(v2) — `load_user` 가 seam(파일→DB 교체).

## 사용자 추가(로컬)
`cp -r users/gonsoo users/<id>` → `profile.yaml`·`skill.md` 편집. (SES sandbox: recipient 사전 verify 필요.)
