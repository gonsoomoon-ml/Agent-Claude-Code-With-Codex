"""areas — 메일이 쓰는 **분야(topic) 6칸**의 단일 정본. 헤드라인 칸·카드 밴드·라벨 프롬프트가 모두 여기서 읽는다.

왜 공용인가(2026-10-24 결정, `docs/superpowers/specs/2026-10-24-topic-grouping-design.md` §4):
한 메일에 분류 어휘가 둘이면 독자가 두 체계를 배워야 한다. 헤드라인 칸(AI타임스 제목)과 카드 밴드(검증 카드)는
같은 이름·같은 순서를 쓰고, 빈 칸은 숨긴다. 축은 **주제(무엇에 관한 글인가) 하나** — 장르(발표·가이드·사례·보도)는
발행처가 76% 결정하므로 묶는 기준에서 뺐다(7일 132편 손분류, `docs/work_note/Oct-2026/261024-Reorder-Content/classify-7d.md`).

- `AREAS`: 영문 이름이 정본(2026-10-18 원칙 — 한국어판·영어판 공통 키). 순서 = 메일 소제목·밴드 순서.
- `AREA_DEFINITIONS`: 카드 라벨 프롬프트용 정의 + 우선 규칙(스펙 §4.1·§4.2). 라벨은 이 목록과 **정확 일치**해야 한다.
- `AREA_DEFINITIONS_HEADLINES`: 제목만 보는 헤드라인 분류용 변형(스펙 §4.3 — 칩·데이터센터 *기술* 뉴스는
  Inference & Hardware, *돈* 뉴스는 Industry & Business; 연구 뉴스는 주제로).
"""
from __future__ import annotations

AREAS: tuple[str, ...] = (
    "AI Agents",
    "Applied AI",
    "Models & Releases",
    "Inference & Hardware",
    "Safety, Security & Policy",
    "Industry & Business",
)

_CORE = (
    "Areas (exactly one per article; use the names verbatim):\n"
    "- AI Agents = agent products and frameworks, agent protocols (MCP, Agent Skills), agentic coding, agent "
    "evaluation and benchmarks, agent sandboxing and isolation, engineering guides about building agents.\n"
    "- Applied AI = AI put to use: a named organization applying AI to its own business (customer and case "
    "studies), domain applications (science, health, earth, a specific industry), and production practice "
    "(gateways, RAG and knowledge bases, observability, cost control, compliance, deployment operations).\n"
    "- Models & Releases = what vendors ship: new or updated models and their capabilities or comparisons "
    "(language, speech, image, video), product and platform launches, and announcements that a model or "
    "platform is now available (availability) somewhere.\n"
    "- Inference & Hardware = serving engines (vLLM, SGLang), KV cache and inference optimization, on-device "
    "inference, training infrastructure, accelerators (Trainium, TPU, NPU, GPU) and data-center technology.\n"
    "- Safety, Security & Policy = security incidents, supply-chain attacks and vulnerabilities, alignment and "
    "safety research, audits and incident assessments, law, regulation and government action.\n"
    "- Industry & Business = funding, deals, partnerships, market analysis, price wars, hiring and "
    "organizational news.\n"
)

AREA_DEFINITIONS: str = _CORE + (
    "Tie-break rules, in order:\n"
    "1. If an agent system is the protagonist, choose AI Agents over Models & Releases or Applied AI (this "
    "includes agent product launches).\n"
    "2. A model or platform becoming available on some platform, or a vendor's new feature or launch, is "
    "Models & Releases, not Industry & Business.\n"
    "3. Engines, chips, training tooling and inference performance are Inference & Hardware regardless of "
    "whether the article is a guide or an announcement.\n"
    "4. Harm, attacks, incidents, audits and law are Safety, Security & Policy rather than AI Agents "
    "(capabilities and benchmarks stay in AI Agents); money, deals and markets alone are Industry & Business.\n"
    "5. A customer or case story - a named organization (other than the vendor itself) applying AI to its own "
    "work - is Applied AI even when the technology is an agent or a chip; this rule wins over rules 1 and 3. A "
    "guide whose subject is the technology itself goes to the technology's area."
)

AREA_DEFINITIONS_HEADLINES: str = _CORE + (
    "For news headlines: technical news about chips or data centers is Inference & Hardware, while money news "
    "about them (investment, earnings, orders) is Industry & Business. Research news is filed by its subject: "
    "AI applied to science or health is Applied AI, agent research is AI Agents, safety research is Safety, "
    "Security & Policy."
)
