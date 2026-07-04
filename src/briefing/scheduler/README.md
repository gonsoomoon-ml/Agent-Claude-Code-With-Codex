# scheduler — ⑤ 발송 체인 어댑터 (EventBridge→Lambda)
`due.py`(발송 대상 판정) → `dispatch.py`(runtime `add_async_task` 호출) → `deliver.py`(SES) · `sent_log.py`(중복 방지) · `run_dispatch.py`(로컬 프리뷰).
`lambda_handler.py` 는 **의도적으로 briefing import 0**(boto3 만) — flat zip(Handler=`lambda_handler.handler`)이라 소스 트리 레이아웃과 무관. invoke_runtime 의 SSE 파서와 "중복 제거" 금지(의도된 복사).
`deploy_scheduler.py`·`teardown_scheduler.sh` = 배포/철거.
