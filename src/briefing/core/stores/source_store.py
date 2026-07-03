"""source_store — 내용으로 주소를 매기는 정본 저장소(content-addressed source-of-record). durable ledger 의 토대.

설계 불변식 (design/architecture/retrieval-gateway-analysis.md §5 + ★확장):
- 권위 페치는 fabric 이 *한 번만* 한다 → 정본 텍스트를 **sha256 으로 동결**해 저장한다.
- author 의 요약도, certifier 의 검증도 *같은 source_id* 의 동결본을 본다 → 바이트 단위로 같음을 보장(anti-cheat).
- **정규화 지점은 단 하나**(normalize) → author·certifier 가 같은 텍스트를 보게 해 정규화 드리프트를 없앤다.
- v1 = 로컬 파일 store(sha256 키, 불변). v1.5 = AgentCore Gateway 의 'identical channel'(S3/DDB).

이 모듈은 결정론적(byte-stable) — 스캐폴드 첫 실행부터 LLM 없이 실제로 동작한다.
"""
from __future__ import annotations

import hashlib
import json
import os
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class FrozenSource:
    source_id: str   # = sha256(정규화된 텍스트) — 내용으로 만든 id
    url: str
    title: str
    text: str        # 정규화된 정본 텍스트(정규화는 한 곳에서만 — author·certifier 가 같은 바이트를 본다)
    fetched_at: str  # ISO8601 시각(결정론을 위해 호출자가 바깥에서 넣어준다)
    media: str = ""  # 발행 매체(예: "AI Times"). 빈값이면 freeze 가 url 도메인에서 유도(→ aitimes.com)


def normalize(text: str) -> str:
    """정규화는 *이 함수 한 곳*에서만 한다 — author·certifier 가 *같은* 텍스트를 보게 해 정규화 드리프트를 없앤다.

    ⚠️ normalize 를 바꾸면 *모든 source_id 가 바뀐다*(해시 입력이 달라지므로) → 원장이 쌓인 뒤에는 사실상 고정(pin)이다.
    TODO: 보일러플레이트 제거 정책을 확정할 것. 지금은 = 개행 통일 + 줄 끝 공백 정리 + NFC.
    """
    unified = text.replace("\r\n", "\n").replace("\r", "\n")
    stripped = "\n".join(line.rstrip() for line in unified.split("\n")).strip()
    return unicodedata.normalize("NFC", stripped)  # 한국어 NFC 로 통일(같은 글자라도 NFC/NFD 면 바이트가 달라 해시가 갈리는 걸 막는다)


def content_id(normalized_text: str) -> str:
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def media_from_url(url: str) -> str:
    """url 에서 발행 매체 도메인을 뽑는다(www. 제거). 예: https://www.aitimes.com/x → aitimes.com.

    catalog 의 Source.name 이 있으면 그게 정본(우선)이고, 이건 그게 없을 때의 fallback 이다.
    """
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


class SourceStore:
    """sha256 키로 내용 주소를 매기는 store. 동결본은 불변(immutable)이다."""

    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, source_id: str) -> Path:
        return self.root / f"{source_id}.json"

    def freeze(self, *, url: str, title: str, raw_text: str, fetched_at: str,
               media: str = "") -> FrozenSource:
        """정본을 정규화·해시해서 동결 저장한다. 동결본은 불변 — 같은 source_id 면 *최초* 동결본을 반환한다(idempotent).

        같은 정규화 텍스트가 다른 url 로 들어와도 source_id 는 같다 → 최초로 들어온 메타데이터가 정본이 된다.
        반환값 == 저장본 == get_source 결과를 보장한다(충돌 시 저장본을 읽어 돌려준다).
        media = 발행 매체(catalog 의 Source.name, 예 "AI Times"); 빈값이면 url 도메인에서 유도한다.
        ★ 원자적 동결: 임시파일에 다 쓴 뒤 os.link 로 거는 게 원자적이라(이미 있으면 FileExistsError), 동시 freeze 에도 첫 동결이
          이기고 부분쓰기 손상도 막는다(크래시 시 임시파일만 남음). DynamoSourceStore 의 조건부 put 과 같은 first-wins 보장.
        """
        text = normalize(raw_text)
        source_id = content_id(text)
        p = self._path(source_id)
        fs = FrozenSource(source_id=source_id, url=url, title=title, text=text,
                          fetched_at=fetched_at, media=media or media_from_url(url))
        tmp = p.with_name(f".{source_id}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(asdict(fs), ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.link(tmp, p)                      # 원자적 — 이미 있으면 FileExistsError(첫 동결이 이긴다)
        except FileExistsError:
            return self.get_source(source_id)    # 충돌 → 최초 동결본을 읽어 반환
        finally:
            tmp.unlink(missing_ok=True)
        return fs

    def get_source(self, source_id: str) -> FrozenSource:
        """동결본을 읽기 전용으로 조회한다(author·gate 가 쓴다; certifier 는 접근 안 함 — envelope 만 받는다).

        없는 source_id 면 KeyError — 미스는 dangling 포인터(있어선 안 될 일)라 조용히 빈 값을 주지 않고 시끄럽게 실패한다.
        (DynamoSourceStore 도 미스 시 KeyError 를 던진다 — 두 backend 파리티.)
        """
        p = self._path(source_id)
        if not p.exists():
            raise KeyError(f"source_id 없음: {source_id}")
        return FrozenSource(**json.loads(p.read_text(encoding="utf-8")))
