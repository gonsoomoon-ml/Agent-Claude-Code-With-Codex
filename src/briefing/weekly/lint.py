"""Field Experiment 기사 md 결정론 검사(lint) — 발송 전 관문.

규칙의 원천은 `field-experiment/README.md` §4(기사 구성 · 그림 규칙) · §6(표기) · §7(저장소 링크)이다.
용어 목록은 같은 폴더 `terms.md`(9번 검사가 읽는다).
여기서는 기계로 잴 수 있는 것만 잰다. ① 첫 줄이 구체적인 장면인지 · 사실 정확성 ·
"한 사실은 한 번"은 재지 않는다(§9 8번 사람 확인 · 데일리 카드/Codex 대조의 몫).
2026-11-04(A 설계): 그림은 고정 2장(② 「엮으면」 뒤 개념도 · ③ AWS 줄 아래 시스템도, 선택 = ① 장면) + 캡션 줄 `그림 N — …`,
그림의 숫자는 본문 숫자이거나 ② 숫자 둘의 합 · 차(7b). ```prompt 블록(③ 실험 조각 ≤6줄 × 80칸, 메일에서는 줄바꿈 허용)은 그림 규칙 면제. 11-07 호 전 기사는 이 규칙 이전.

실행: uv run python -m briefing.weekly.lint field-experiment/issues/YYYY-MM-DD.md
종료 코드: FAIL 이 하나라도 있으면 1, 아니면 0(경고는 통과).
"""
import re
import sys
import unicodedata
from pathlib import Path

MAX_CHARS, TARGET_CHARS = 3000, 2600
SECTION_TARGET = {"0": 250, "①": 250, "②": 1000, "③": 800, "④": 200}  # README §4 표의 "~" 목표
WARN_RATIO = 1.25  # 목표의 1.25배를 넘으면 경고(목표가 근사치라 FAIL 아님)
FLOW_MAX_LINES, FLOW_MAX_CELLS = 15, 40
PROMPT_MAX_LINES, PROMPT_MAX_CELLS = 6, 80   # ```prompt 실험 조각(③) — 그림이 아니다
MIN_FIGURES, MIN_REPO_LINKS, MAX_REPO_LINKS = 2, 2, 3
FIGURE_SECTIONS = ("②", "③")                 # 고정 그림 자리: 개념도(②) · 시스템도(③)
NUM_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")   # 7b 그림 숫자 근거 — 값으로 비교(36%p · 4.00 · 1,234)
CAPTION_RE = re.compile(r"^그림\s*\d+\s*[—-]")
SECTIONS = ["①", "②", "③", "④"]

URL_RE = re.compile(r"https?://[^\s)>\]]+")
MD_LINK_RE = re.compile(r"\[([^\]]*)\]\((?:[^)]*)\)")
REPO_RE = re.compile(r"https?://(?:www\.)?(?:github\.com|gitlab\.com)/([^/\s)]+/[^/\s)#?]+)")
TABLE_RE = re.compile(r"^\s*\|.*\|\s*$")
# 독자 본문 금지 표식(§4 · §6). '(제안)'은 ③ 제목에 정당하게 쓰이므로 제외.
MARKER_RE = re.compile(r"✓|(?:\*\*|\(|\[)\s*(?:확인 필요|미검증|격리)\s*(?:\*\*|\)|\])")
# 중괄호 자리표시(`{값}`) — 작성자가 모르는 값을 틀로 남긴 것(2026-11-04 Opus 재생성 "세션당 예산 {값}" 실측). 코드 블록(```prompt 의
# `{k}` `{lean}` 은 변수) 밖에서만 본다.
PLACEHOLDER_RE = re.compile(r"\{[^{}\n]{1,30}\}")
# 그림 금지 기호: 박스 문자 · 블록 · 도형(▼▶●) · 화살표(→↓)
FORBIDDEN_FLOW = [(0x2500, 0x257F), (0x2580, 0x259F), (0x25A0, 0x25FF), (0x2190, 0x21FF)]


TERMS_PATH = Path(__file__).resolve().parent / "terms.md"


def load_terms(path: Path = TERMS_PATH) -> list[tuple[str, str, str]]:
    """templates/terms.md 표 → (쓰지 않을 말, 쓸 말, 판정) 목록."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cols) >= 4 and cols[3] in ("FAIL", "WARN"):
            rows.append((cols[0], cols[1], cols[3]))
    return rows


def cells(ch: str) -> int:
    """고정폭 글꼴에서 차지하는 칸 수 — 한글 등 전각(W·F)은 2칸."""
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def visible_len(text: str) -> int:
    """링크 주소 · 줄바꿈 · 줄머리 들여쓰기 · md 기호를 뺀 글자 수(문장 안 공백은 포함)."""
    text = MD_LINK_RE.sub(r"\1", text)
    text = URL_RE.sub("", text)
    text = re.sub(r"^[ \t]+", "", text, flags=re.M)  # 들여쓰기(그림 · 중첩 목록)는 읽는 글자가 아니다
    text = re.sub(r"^#+\s*", "", text, flags=re.M)
    text = re.sub(r"^[-*]\s+", "", text, flags=re.M)
    text = re.sub(r"^`{3}.*$", "", text, flags=re.M)
    text = text.replace("**", "").replace("`", "")
    return len(text.replace("\n", ""))


def parse(md: str):
    """섹션(0 · ①~④ · 출처)별 줄 목록과 코드 블록(섹션, 줄들)을 돌려준다."""
    sections = {"0": []}
    blocks, order = [], []
    cur, in_code, buf, lang = "0", False, [], ""
    for line in md.splitlines():
        if line.strip().startswith("```"):
            if in_code:
                blocks.append((cur, buf, lang))
                buf = []
            else:
                lang = line.strip()[3:].strip().lower()
            in_code = not in_code
            sections[cur].append(line)
            continue
        if in_code:
            buf.append(line)
        elif line.startswith("## "):
            cur = next((s for s in SECTIONS if s in line), line[3:].strip())
            order.append(cur)
            sections.setdefault(cur, [])
        elif line.strip().strip("*").strip() == "출처":
            cur = "src"
            sections.setdefault(cur, [])
        sections[cur].append(line)
    return sections, blocks, order, in_code


def _nums(text: str) -> set[float]:
    """텍스트의 숫자 값 집합(콤마 제거 · 소수 허용). 링크 주소는 뺀다."""
    return {float(m.replace(",", "")) for m in NUM_RE.findall(URL_RE.sub("", text))}


def allowed_figure_numbers(md: str) -> set[float]:
    """그림(ASCII · 이미지 스펙)에 쓸 수 있는 숫자 — 본문(그림 밖) 숫자 ∪ ② 숫자 둘의 합 · 차(README §4: 36%p = 86 − 50)."""
    sections, blocks, _, _ = parse(md)
    prose_lines, in_code = [], False
    for key in ["0", *SECTIONS]:
        for line in sections.get(key, []):
            if line.strip().startswith("```"):
                in_code = not in_code
            elif not in_code:
                prose_lines.append(line)
    two = _nums("\n".join(ln for ln in sections.get("②", []) if not ln.strip().startswith("```")))
    return _nums("\n".join(prose_lines)) | {round(a + b, 6) for a in two for b in two} | {round(abs(a - b), 6) for a in two for b in two}


def _fmt(v: float) -> str:
    return str(int(v)) if v == int(v) else str(v)


def _opens_figure(lines: list[str], i: int) -> bool:
    """i 번째 줄이 그림(prompt 아님)을 *여는* ``` 인가 — 앞선 ``` 수가 짝수면 여는 줄."""
    opens = sum(1 for ln in lines[:i] if ln.strip().startswith("```")) % 2 == 0
    return opens and lines[i].strip()[3:].strip().lower() != "prompt"


def _prev_text(lines: list[str], i: int) -> str:
    """i 앞의 비어 있지 않은 줄."""
    for ln in reversed(lines[:i]):
        if ln.strip():
            return ln.strip()
    return ""


def check_figure(lines: list[str]) -> list[str]:
    """그림 규칙 1)~3)(README §4) 위반 목록."""
    errs = []
    if len(lines) > FLOW_MAX_LINES:
        errs.append(f"{len(lines)}줄 > {FLOW_MAX_LINES}줄")
    for n, line in enumerate(lines, 1):
        width = sum(cells(c) for c in line)
        if width > FLOW_MAX_CELLS:
            errs.append(f"{n}행 {width}칸 > {FLOW_MAX_CELLS}칸")
        if "\t" in line:
            errs.append(f"{n}행 탭 문자")
        bad = sorted({c for c in line if any(a <= ord(c) <= b for a, b in FORBIDDEN_FLOW)})
        if bad:
            errs.append(f"{n}행 ASCII 아닌 연결 기호 {''.join(bad)}")
        wide = next((i for i, c in enumerate(line) if cells(c) == 2), None)
        if wide is not None:
            tail = line[wide:]
            if re.search(r"\S {2,}\S", tail):
                errs.append(f"{n}행 한글 뒤 칸 맞춤(공백 2개 이상)")
            if tail.rstrip().endswith(("|", "+")):
                errs.append(f"{n}행 한글 뒤 오른쪽 테두리")
    return errs


def lint(md: str) -> list[tuple[str, str, str]]:
    """(판정, 번호, 메시지) 목록. 판정 = PASS · WARN · FAIL."""
    out = []
    sections, blocks, order, unclosed = parse(md)
    body_keys = ["0"] + SECTIONS
    body = "\n".join("\n".join(sections.get(k, [])) for k in body_keys)

    # 1 글자 수
    total = visible_len(body)
    verdict = "FAIL" if total > MAX_CHARS else "WARN" if total > TARGET_CHARS else "PASS"
    out.append((verdict, "1", f"본문 {total:,}자 (상한 {MAX_CHARS:,} · 목표 ~{TARGET_CHARS:,}, 출처 제외)"))

    # 2 구성
    errs = []
    if "실험 한 줄" not in "\n".join(sections["0"]):
        errs.append("실험 한 줄 없음")
    if [s for s in order if s in SECTIONS] != SECTIONS:
        errs.append(f"섹션 순서 {order} ≠ {SECTIONS}")
    src_urls = URL_RE.findall("\n".join(sections.get("src", [])))
    if not src_urls:
        errs.append("출처 URL 없음")
    out.append(("FAIL" if errs else "PASS", "2", "구성: " + ("; ".join(errs) or "실험 한 줄 · ①~④ · 출처")))
    if src_urls and len(src_urls) != 3:
        out.append(("WARN", "2", f"출처 URL {len(src_urls)}개 (README: 3개)"))

    # 3 표 · 4 표식 — 코드 블록 안은 제외
    plain = []
    in_code = False
    for line in body.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
        elif not in_code:
            plain.append(line)
    tables = [line for line in plain if TABLE_RE.match(line)]
    out.append(("FAIL" if tables else "PASS", "3", f"표 줄 {len(tables)}개"))
    markers = sorted({m.group(0) for line in plain for m in MARKER_RE.finditer(line)})
    markers += [f"자리표시 {h}" for h in sorted({m.group(0) for line in plain for m in PLACEHOLDER_RE.finditer(line)})]
    out.append(("FAIL" if markers else "PASS", "4", "표식 " + (", ".join(markers) or "없음")))

    # 5 저장소 링크
    errs = []
    for key, lines in sections.items():
        repos = set(REPO_RE.findall("\n".join(lines)))
        if key != "③" and repos:
            errs.append(f"{key} 에 저장소 링크 {sorted(repos)}")
        if key == "③" and len(repos) > MAX_REPO_LINKS:
            errs.append(f"③ 저장소 {len(repos)}개 > {MAX_REPO_LINKS}")
    n3 = len(set(REPO_RE.findall("\n".join(sections.get("③", [])))))
    out.append(("FAIL" if errs else "PASS", "5", "저장소 링크: " + ("; ".join(errs) or f"③ 에만 {n3}개")))
    if not errs and n3 < MIN_REPO_LINKS:
        out.append(("WARN", "5", f"③ 시작점(코드) {n3}줄 (README §7: 2~3줄)"))

    # 6 내 시스템에 대입
    has = "내 시스템에 대입" in "\n".join(sections.get("③", []))
    out.append(("PASS" if has else "FAIL", "6", "③ '내 시스템에 대입' 줄 " + ("있음" if has else "없음")))

    # 7 그림(``` 블록, prompt 제외): 모양 규칙 1)~3) + 고정 2장(② · ③) + 캡션 줄. ```prompt 는 ③ 실험 조각(별도 한도)
    figures = [(k, ls) for k, ls, lang in blocks if lang != "prompt"]
    prompts = [(k, ls) for k, ls, lang in blocks if lang == "prompt"]
    errs = []
    if unclosed:
        errs.append("닫히지 않은 ``` 블록")
    for n, (key, lines) in enumerate(figures, 1):
        errs += [f"그림{n}({key}) {e}" for e in check_figure(lines)]
    if len(figures) < MIN_FIGURES:
        errs.append(f"그림 {len(figures)}개 < {MIN_FIGURES}(개념도 ② · 시스템도 ③)")
    for sec in FIGURE_SECTIONS:
        if not any(k == sec for k, _ in figures):
            errs.append(f"{sec} 에 그림 없음")
    for n, (key, lines) in enumerate(prompts, 1):
        if key != "③":
            errs.append(f"prompt 조각이 ③ 밖({key})")
        if len(lines) > PROMPT_MAX_LINES:
            errs.append(f"prompt 조각 {len(lines)}줄 > {PROMPT_MAX_LINES}줄")
        errs += [f"prompt 조각 {i}행 {w}칸 > {PROMPT_MAX_CELLS}칸" for i, w in
                 ((i, sum(cells(c) for c in ln)) for i, ln in enumerate(lines, 1)) if w > PROMPT_MAX_CELLS]
    if len(prompts) > 1:
        errs.append(f"prompt 조각 {len(prompts)}개 > 1")
    out.append(("FAIL" if errs else "PASS", "7", "그림 모양: " + ("; ".join(errs) or f"규칙 통과(그림 {len(figures)}개 · 조각 {len(prompts)}개)")))
    missing_caps = [i for i, line in enumerate(body.splitlines()) if line.strip().startswith("```") and i > 0
                    and _opens_figure(body.splitlines(), i) and not CAPTION_RE.match(_prev_text(body.splitlines(), i))]
    if missing_caps:
        out.append(("WARN", "7", f"캡션 줄(`그림 N — …`) 없는 그림 {len(missing_caps)}개"))
    where = ", ".join(f"{k} {len(v)}줄" for k, v in figures) or "없음"
    out.append(("INFO", "7", f"그림 {len(figures)}개 — {where} · 조각 {len(prompts)}개 (run 로그에 옮김)"))

    # 7b 그림 숫자 근거: 그림의 숫자는 본문(그림 밖) 숫자이거나 ② 숫자 둘의 합 · 차(README §4 예시의 36%p = 86 - 50)
    allowed = allowed_figure_numbers(md)
    stray = sorted({v for _, lines in figures for v in _nums("\n".join(lines)) if v not in allowed})
    out.append(("FAIL" if stray else "PASS", "7b", "그림 숫자 근거: " + (f"본문에 없는 숫자 {[_fmt(v) for v in stray]}" if stray else "전부 본문 · ② 합차 안")))

    # 8 섹션별 분량(경고만)
    for key, target in SECTION_TARGET.items():
        n = visible_len("\n".join(sections.get(key, [])))
        if n > target * WARN_RATIO:
            out.append(("WARN", "8", f"{key} {n:,}자 (목표 ~{target:,})"))

    # 9 용어(templates/terms.md) — 낱말 바로 앞이 한글이 아닐 때만 맞춘다
    if not TERMS_PATH.exists():
        out.append(("WARN", "9", f"용어 목록 없음: {TERMS_PATH}"))
    else:
        terms = load_terms()
        hits = {"FAIL": [], "WARN": []}
        for term, use, level in terms:
            n = len(re.findall(r"(?<![가-힣])" + re.escape(term), body))
            if n:
                hits[level].append(f"'{term}' {n}회 → {use}")
        if hits["FAIL"]:
            out.append(("FAIL", "9", "용어: " + "; ".join(hits["FAIL"])))
        out += [("WARN", "9", "용어: " + h) for h in hits["WARN"]]
        if not any(hits.values()):
            out.append(("PASS", "9", f"용어 목록 {len(terms)}개 해당 없음"))
    return out


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    path = Path(sys.argv[1])
    results = lint(path.read_text(encoding="utf-8"))
    print(f"lint {path}")
    for verdict, num, msg in results:
        print(f"  {verdict:4} {num}  {msg}")
    fails = sum(v == "FAIL" for v, _, _ in results)
    print(f"→ {'FAIL ' + str(fails) + '건' if fails else 'PASS'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
