"""source_store — content-addressed source-of-record (durable ledger 의 토대).

설계 불변식 (design/architecture/retrieval-gateway-analysis.md §5 + ★확장):
- 권위 페치는 fabric 이 *1회* 수행 → 정본 텍스트를 **sha256 으로 동결**해 저장.
- author 요약·certifier 검증은 *같은 source_id* 의 동결본을 봄 → 바이트 동일성 보장(anti-cheat).
- **단일 정규화 지점**(normalize) → author·certifier 가 같은 텍스트를 봐 정규화 드리프트 제거.
- v1 = 로컬 파일 store(sha256 키, 불변). v1.5 = AgentCore Gateway 'identical channel'(S3/DDB).

이 모듈은 결정론(byte-stable) — 스캐폴드 첫 실행부터 실제 동작한다(LLM 불필요).
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class FrozenSource:
    source_id: str   # = sha256(normalized text) — content-addressed id
    url: str
    title: str
    text: str        # 정규화된 정본 (단일 정규화 — author·certifier 가 같은 바이트)
    fetched_at: str  # ISO8601 (결정론 위해 호출자가 외부 주입)
    media: str = ""  # 발행 매체(예: "AI Times"); 빈값이면 freeze 가 url 도메인으로 유도(→ aitimes.com)


def normalize(text: str) -> str:
    """단일 정규화 지점 — author·certifier 가 *같은* 텍스트를 보게 함(정규화 드리프트 제거).

    ⚠️ normalize 변경은 *모든 source_id 를 바꾼다*(해시 입력이 바뀌므로) → 원장이 쌓인 뒤엔 사실상 pin.
    TODO: 보일러플레이트 제거 정책 확정. 지금 = 개행 통일 + 말미공백 정리 + NFC.
    """
    unified = text.replace("\r\n", "\n").replace("\r", "\n")
    stripped = "\n".join(line.rstrip() for line in unified.split("\n")).strip()
    return unicodedata.normalize("NFC", stripped)  # 한국어 NFC 통일 (NFC/NFD 해시 분기 방지)


def content_id(normalized_text: str) -> str:
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def media_from_url(url: str) -> str:
    """url → 발행 매체 도메인(www. 제거). 예: https://www.aitimes.com/x → aitimes.com.

    catalog 의 Source.name 이 주어지면 그게 우선(정본); 이건 미제공 시 fallback.
    """
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


class SourceStore:
    """sha256 키 content-addressed store. 동결본은 불변(immutable)."""

    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, source_id: str) -> Path:
        return self.root / f"{source_id}.json"

    def freeze(self, *, url: str, title: str, raw_text: str, fetched_at: str,
               media: str = "") -> FrozenSource:
        """정본을 정규화·해시·동결 저장. 동결본은 불변 — 같은 source_id 면 *최초* 동결본을 반환(idempotent).

        같은 정규화 텍스트가 다른 url 로 와도 source_id 동일 → 최초 메타데이터가 정본.
        반환 == 저장 == get_source 를 보장(충돌 시 저장본을 읽어 반환).
        media = 발행 매체(catalog Source.name, 예 "AI Times"); 빈값이면 url 도메인으로 유도.
        """
        text = normalize(raw_text)
        source_id = content_id(text)
        p = self._path(source_id)
        if p.exists():
            return self.get_source(source_id)
        fs = FrozenSource(source_id=source_id, url=url, title=title, text=text,
                          fetched_at=fetched_at, media=media or media_from_url(url))
        p.write_text(json.dumps(asdict(fs), ensure_ascii=False, indent=2), encoding="utf-8")
        return fs

    def get_source(self, source_id: str) -> FrozenSource:
        """동결본 read-only 조회 (author·gate 가 사용; certifier 는 미접근 — envelope-fed)."""
        return FrozenSource(**json.loads(self._path(source_id).read_text(encoding="utf-8")))
