"""Markdown 구조 단위의 결정적 열거·정규화·식별(core.yaml packet_semantics.coverage).

지원 범위(명시적 한계):
- heading은 ATX(`#`)만 인식한다. setext heading은 문단으로 취급한다.
- table은 `|`로 시작하는 GFM table만 인식한다.
- blockquote 안의 list·code는 문단 텍스트로 취급한다.
이 한계는 도구 출력의 not_checked에 포함된다.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field

HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
LIST_ITEM = re.compile(r"^([ \t]*)([-*+]|\d+[.)])[ \t]+(.*)$")
TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$")
THEMATIC_BREAK = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
NUMBER_PREFIX = re.compile(r"^(\d+(?:\.\d+)*)\.?(?:\s|$)")
LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
EXCERPT_START = 20
EXCERPT_STEP = 5

LIMITATIONS = [
    "setext heading 미인식(문단 취급)",
    "선행 `|` 없는 table 미인식",
    "blockquote 안의 list·code는 문단 텍스트로 취급",
]


def normalize(text: str) -> str:
    """NFC → 링크 표시 텍스트 → 강조 표식 제거 → 공백 정리. marker·table 연결은 열거 단계에서 한다."""
    value = unicodedata.normalize("NFC", text)
    value = LINK.sub(r"\1", value)
    for mark in ("**", "__", "`", "*"):
        value = value.replace(mark, "")
    return re.sub(r"\s+", " ", value).strip()


def fingerprint(norm: str) -> str:
    return "sha256:" + hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


@dataclass
class Heading:
    line: int
    level: int
    text: str
    norm: str
    number: str | None


@dataclass
class Unit:
    artifact: str
    kind: str
    line: int
    path: tuple[str, ...]
    ordinal: int
    raw: str
    norm: str = field(init=False)
    fp: str = field(init=False)

    def __post_init__(self) -> None:
        self.norm = normalize(self.raw)
        self.fp = fingerprint(self.norm)

    @property
    def hint(self) -> str:
        return " > ".join(self.path) + f" #{self.ordinal}"


def headings(lines: list[str]) -> list[Heading]:
    found: list[Heading] = []
    fence: str | None = None
    for index, line in enumerate(lines):
        mark = FENCE.match(line)
        if fence:
            if mark and mark.group(1)[0] == fence[0] and len(mark.group(1)) >= len(fence):
                fence = None
            continue
        if mark:
            fence = mark.group(1)
            continue
        match = HEADING.match(line)
        if match:
            text = match.group(2)
            norm = normalize(text)
            number = NUMBER_PREFIX.match(norm)
            found.append(Heading(index, len(match.group(1)), text, norm, number.group(1) if number else None))
    return found


def _matches(component: str, heading: Heading) -> bool:
    wanted = normalize(component)
    return heading.norm == wanted or (heading.number is not None and heading.number == wanted)


def resolve_section(lines: list[str], selector: str) -> tuple[tuple[int, int] | None, str | None]:
    """heading 경로(' > ' 구분)를 (본문 시작 줄, 끝 줄)로 해석한다."""
    items = headings(lines)
    components = [c.strip() for c in selector.split(" > ") if c.strip()]
    if not components:
        return None, "빈 section 경로"
    start, end, level = 0, len(lines), 0
    chosen: Heading | None = None
    for component in components:
        candidates = [h for h in items if start <= h.line < end and h.level > level and _matches(component, h)]
        if len(candidates) != 1:
            state = "없음" if not candidates else f"{len(candidates)}개와 일치"
            return None, f"section 경로 해석 실패({component}: {state})"
        chosen = candidates[0]
        level = chosen.level
        later = [h for h in items if h.line > chosen.line and h.level <= chosen.level]
        start, end = chosen.line, (later[0].line if later else len(lines))
    assert chosen is not None
    return (chosen.line, end), None


def _heading_path(items: list[Heading], line: int) -> tuple[str, ...]:
    stack: list[Heading] = []
    for heading in items:
        if heading.line >= line:
            break
        while stack and stack[-1].level >= heading.level:
            stack.pop()
        stack.append(heading)
    return tuple(h.norm for h in stack)


def _table_row(line: str) -> str:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    cells = [c.strip() for c in re.split(r"(?<!\\)\|", body)]
    return " | ".join(cells)


def enumerate_range(artifact: str, lines: list[str], start: int, end: int) -> list[Unit]:
    """[start, end) 줄 범위의 구조 단위. start 줄이 heading이면 단위가 아니다."""
    items = headings(lines)
    heading_lines = {h.line for h in items}
    raw_units: list[tuple[str, int, str]] = []
    i = start
    current_item: list | None = None  # [kind, line, text_parts, content_indent]

    def flush_item() -> None:
        nonlocal current_item
        if current_item is not None:
            raw_units.append((current_item[0], current_item[1], "\n".join(current_item[2])))
            current_item = None

    while i < end:
        line = lines[i]
        stripped = line.strip()
        if i in heading_lines:
            flush_item()
            i += 1
            continue
        mark = FENCE.match(line)
        if mark:
            flush_item()
            fence = mark.group(1)
            i += 1
            while i < end:
                closing = FENCE.match(lines[i])
                if closing and closing.group(1)[0] == fence[0] and len(closing.group(1)) >= len(fence):
                    i += 1
                    break
                if lines[i].strip():
                    raw_units.append(("code", i, lines[i].strip()))
                i += 1
            continue
        if THEMATIC_BREAK.match(line):
            flush_item()  # 구분선은 단위가 아니다(CommonMark상 list item보다 우선)
            i += 1
            continue
        if stripped.startswith("<!--"):
            flush_item()
            while i < end and "-->" not in lines[i]:
                i += 1
            i += 1
            continue
        if not stripped:
            # 빈 줄 뒤 들여쓴 비-marker 줄은 같은 list item의 계속 문단이다.
            if current_item is not None:
                j = i + 1
                while j < end and not lines[j].strip():
                    j += 1
                if j < end and j not in heading_lines:
                    nxt = lines[j]
                    indent = len(nxt) - len(nxt.lstrip())
                    if indent >= current_item[3] and not LIST_ITEM.match(nxt) and not FENCE.match(nxt):
                        current_item[2].append(nxt.strip())
                        i = j + 1
                        continue
                flush_item()
            i += 1
            continue
        if stripped.startswith("|") and i + 1 < end and TABLE_SEP.match(lines[i + 1]):
            flush_item()
            i += 2
            while i < end and lines[i].strip().startswith("|"):
                raw_units.append(("row", i, _table_row(lines[i])))
                i += 1
            continue
        item = LIST_ITEM.match(line)
        if item:
            flush_item()
            indent = len(item.group(1).expandtabs(4))
            content_indent = indent + len(item.group(2)) + 1
            current_item = [f"li{indent // 2 if indent else 0}", i, [item.group(3)], content_indent]
            i += 1
            continue
        if stripped.startswith(">"):
            flush_item()
            # 인용 안의 문단마다 자기 시작 줄 번호를 쓴다(다른 단위와 줄 번호가 겹치지 않게).
            quoted: list[str] = []
            quote_start: int | None = None
            while i < end and lines[i].strip().startswith(">"):
                inner = re.sub(r"^\s*>\s?", "", lines[i]).strip()
                if inner:
                    quote_start = i if quote_start is None else quote_start
                    quoted.append(inner)
                elif quoted:
                    raw_units.append(("quote", quote_start, "\n".join(quoted)))
                    quoted, quote_start = [], None
                i += 1
            if quoted:
                raw_units.append(("quote", quote_start, "\n".join(quoted)))
            continue
        if current_item is not None:
            current_item[2].append(stripped)  # lazy continuation
            i += 1
            continue
        paragraph_start = i
        paragraph = [stripped]  # 첫 줄은 항상 소비한다(separator 없는 `|` 줄 등)
        i += 1
        while i < end and lines[i].strip() and i not in heading_lines:
            if FENCE.match(lines[i]) or LIST_ITEM.match(lines[i]) or lines[i].strip().startswith(("|", ">", "<!--")):
                break
            paragraph.append(lines[i].strip())
            i += 1
        raw_units.append(("para", paragraph_start, "\n".join(paragraph)))
    flush_item()

    lines_used = [line_no for _, line_no, _ in raw_units]
    assert len(lines_used) == len(set(lines_used)), "구조 단위의 시작 줄이 겹친다"
    units: list[Unit] = []
    counters: dict[tuple[str, ...], int] = {}
    for kind, line_no, raw in sorted(raw_units, key=lambda u: u[1]):
        if not normalize(raw):
            continue  # 정규화 전문이 빈 줄 조각은 단위가 아니다
        path = _heading_path(items, line_no)
        counters[path] = counters.get(path, 0) + 1
        units.append(Unit(artifact, kind, line_no, path, counters[path], raw))
    return units


def enumerate_sections(artifact: str, text: str, sections: list[str]) -> tuple[list[Unit], list[str]]:
    """선언 section들의 단위(줄 위치로 중복 제거)와 해석 오류."""
    lines = text.splitlines()
    errors: list[str] = []
    ranges: list[tuple[int, int]] = []
    for selector in sections:
        resolved, error = resolve_section(lines, selector)
        if error:
            errors.append(f"{selector}: {error}")
        else:
            ranges.append(resolved)
    seen: set[tuple[int, str]] = set()
    units: list[Unit] = []
    for start, end in sorted(ranges):
        for unit in enumerate_range(artifact, lines, start, end):
            key = (unit.line, unit.raw)  # 겹치는 section 선언의 중복만 제거한다
            if key not in seen:
                seen.add(key)
                units.append(unit)
    units.sort(key=lambda u: u.line)
    return units, errors


def excerpt_for(norm: str, universe: list[str]) -> str:
    """scope 안에서 앞부분이 유일해지는 가장 짧은 excerpt(20자부터 5자씩)."""
    if len(norm) <= EXCERPT_START:
        return norm
    length = EXCERPT_START
    while length < len(norm):
        candidate = norm[:length]
        if sum(1 for other in universe if other.startswith(candidate)) == 1:
            return candidate
        length += EXCERPT_STEP
    return norm


def locate(excerpt: str, units: list[Unit], hint: str | None = None) -> list[Unit]:
    """excerpt로 시작하는 단위들. 여럿이면 hint가 정확히 하나를 고를 때만 좁힌다."""
    wanted = normalize(excerpt)
    found = [u for u in units if u.norm.startswith(wanted)]
    if len(found) > 1 and hint:
        narrowed = [u for u in found if u.hint == hint]
        if len(narrowed) == 1:
            return narrowed
    return found
