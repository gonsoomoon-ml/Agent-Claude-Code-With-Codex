"""Bedrock Converse + Haiku 5.5: effort·thinking 필드 수용 여부 스모크(읽기 전용, 짧은 호출)."""
from botocore.exceptions import ClientError
from briefing.core.config import load_settings
from briefing.core.retrieval.relevance_bedrock import _client

s = load_settings()
c = _client(s.region)
msg = [{"role": "user", "content": [{"text": "Is 17 a prime number? Answer only JSON: {\"prime\": true|false}"}]}]
for label, fields in [
    ("none", None),
    ("effort=high", {"output_config": {"effort": "high"}}),
    ("effort=low", {"output_config": {"effort": "low"}}),
    ("adaptive+high", {"thinking": {"type": "adaptive"}, "output_config": {"effort": "high"}}),
]:
    kw = dict(modelId=s.relevance_model_id, messages=msg, inferenceConfig={"maxTokens": 2000})
    if fields:
        kw["additionalModelRequestFields"] = fields
    try:
        r = c.converse(**kw)
        blocks = r["output"]["message"]["content"]
        print(f"{label:14} OK kinds={[next(iter(b)) for b in blocks]} out={r['usage']['outputTokens']} stop={r['stopReason']}")
    except ClientError as e:
        print(f"{label:14} ERR {e.response['Error']['Code']}: {e.response['Error']['Message'][:160]}")
