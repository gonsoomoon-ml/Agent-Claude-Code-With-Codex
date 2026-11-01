"""#5 — 그림자 검사 qualifier_dropped 의 오탐 원인 확인 + 패치 후보 효과(읽기 전용, 저장소 무변경).

가설: `_RE_QUAL_AFTER` 가 숫자 **바로 뒤** 한 덩어리(≤4자)만 허용해 한국어 관용 표기
'23만 명 이상'(단위어 만 + 조수사 명 + 한정어) · '2억 5천만 끼 이상'(복합 수사) 의 한정어를 못 본다.
패치 후보: 숫자 뒤 수사·단위 글자(만억조천백십·공백·쉼표)를 건너뛴 뒤, 낱말 덩어리 ≤2개 뒤의 한정어까지 인정.
"""
from __future__ import annotations

import re

from briefing.core import quality_checks as qc

# (요약 문장, 원문 문장) — 10-21~29 운영 WARN 13건(qualifier_cases.py 복원) + 합성 진양성(TP) 4건
OPS = [
    ("Hunger는 지금까지 2억 5천만 끼 이상을 배달했고 과거 59개국에서 활동했다.", "Hunger reports delivering more than 250 million meals."),
    ("Anthropic은 직원 23만 명 이상, 60개국에서 사업을 운영하는 HCLTech와 파트너십을 맺었다.", "a global technology company with more than 230,000 people in 60 countries."),
    ("WHO는 매년 25만 명 이상이 임신 관련 합병증으로 사망한다고 추산한다.", "WHO estimates that more than 250,000 preventable deaths occur worldwide each year."),
    ("Recursive는 Flint가 500억 개 미만 매개변수의 MoE 모델 중 선두라고 주장한다.", "among MoE models with fewer than 50 billion parameters."),
    ("90명 이상의 임상의가 2만5000건 이상의 흉부 X선을 판독했다.", "over 90 clinicians have evaluated more than 25,000 chest radiographs."),
    ("MedGemma(출시 이후 다운로드 1000만 회 이상)로 전환했다.", "Since its launch, MedGemma has seen more than 10 million downloads worldwide."),
    ("Replit은 연 1억 달러 이상 계약에 대해 OpenAI가 30% 넘는 할인을 제시하자 옮겼다.", "Replit switched after OpenAI offered more than 30 percent off a contract worth over $100 million a year."),
    ("고객 5곳이 매출의 25%를 차지한다.", "roughly 5 to 7 percent comes from customers who violate usage policies. No single customer accounts for more than ten percent of revenue, but five customers together make up 25 percent."),
    ("동시성 16에서 TTFT p95는 ECS single 5.719초, ECS scaleout 3.612초였다.", "동시성 16에서 TTFT p95가 5.719초까지 증가했습니다."),
    ("지금까지 40만 건 넘는 퀘스트가 완료됐고 10개 언어로 현지화됐다.", "More than 400,000 quests have been completed to date, localized to 10 languages."),
    ("BABILong에서는 10M 토큰까지 거의 완벽한 확장성을 보여 GPT-4와 Titans를 앞섰다.", "our sleep method demonstrated near-perfect scaling up to 10M tokens, outperforming GPT-4 and Titans."),
    ("8만 6,900개 넘는 연구 수준 미해결 문제를 담은 MathDB 기반 벤치마크를 만든다.", "MathDB, which contains more than 86,900 research-level open problems."),
    ("현재 10만 개 넘는 Android 앱이 LiteRT 또는 TensorFlow Lite를 자체 번들하고 있다.", "More than 100K Android apps bundle their own copy of LiteRT or TensorFlow Lite today."),
    ("gnomAD(80만 명 이상의 DNA 데이터를 모은 참조 자료)가 포함된다.", "pools DNA data from over 800,000 people into an open reference"),
]
TP = [  # 진짜 탈락 — 패치 뒤에도 걸려야 한다
    ("새 커널로 추론이 2배 빨라졌다.", "the new kernel makes inference up to 2x faster."),
    ("HCLTech는 직원 23만 명을 보유한 기업이다.", "a global technology company with more than 230,000 people"),
    ("퀘스트 40만 건이 완료됐다.", "More than 400,000 quests have been completed to date"),
    ("지연이 50ms로 줄었다.", "latency dropped to roughly 50ms in our tests"),
]

# ── 패치 후보 ─────────────────────────────────────────────────────────────────
_SKIP = ",. 만억조천백십"
_RE_QUAL_AFTER2 = re.compile(rf"^\s*(?:[^\s\d.,]{{1,4}}\s*){{0,2}}(?:{qc._KO_QUAL_AFTER})")


def _occurrences2(text: str):
    out = []
    for m in qc._RE_DIGITS.finditer(text):
        vals = qc._nums(text[m.start():qc._number_end(text, m.end())])
        j = m.end()
        while j < len(text) and (text[j].isdigit() or text[j] in _SKIP):   # 복합 수사·단위어 건너뛰기
            j += 1
        q = (qc._RE_QUAL_BEFORE.search(text[max(0, m.start() - 16):m.start()])
             or _RE_QUAL_AFTER2.search(text[j:j + 14]))
        out.append((vals, " ".join(q.group().split()).strip("$ ") if q else ""))
    return out


def qualifier_dropped2(summary: str, source: str) -> list[str]:
    src_occ = _occurrences2(source)
    qual_of: dict[float, str] = {}
    for vals, q in src_occ:
        for v in vals:
            if q:
                qual_of.setdefault(v, q)
    bare = qc._union(v for v, q in src_occ if not q)
    hits = {}
    for vals, q in _occurrences2(summary):
        for v in vals:
            if q or qc._is_year(v) or qc.numeric.contains(v, bare):
                continue
            src_q = next((qq for sv, qq in qual_of.items() if qc.numeric.contains(v, {sv})), "")
            if src_q:
                hits[v] = src_q
    return [f"{qc._fmt([v])}({hits[v]})" for v in sorted(hits)]


def main() -> int:
    for label, pairs in (("운영 WARN 13건(오탐 의심)", OPS), ("합성 진양성 4건", TP)):
        print(f"\n### {label}")
        for s, src in pairs:
            now = qc._qualifier_dropped(s, src)
            new = qualifier_dropped2(s, src)
            print(f"  now={str(now):40s} patched={str(new):28s} | {s[:48]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
