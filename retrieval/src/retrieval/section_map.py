from __future__ import annotations

import json
import re
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

SECTION_MAP_VERSION = "1.0"


# Ordered roughly as a Hong Kong prospectus is laid out.  The aliases are
# deliberately conservative: a main-section anchor should be a page header or
# an exact title, not an arbitrary mention in body text.
CANONICAL_SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "summary": ("概要", "摘要", "summary"),
    "definitions": ("釋義", "释义", "definitions"),
    "glossary": ("技術詞彙表", "技术词汇表", "glossary"),
    "forward_looking_statements": ("前瞻性陳述", "前瞻性陈述", "forward-looking statements"),
    "risk_factors": ("風險因素", "风险因素", "risk factors"),
    "waivers": ("豁免及免除", "豁免", "waivers"),
    "offering_information": ("有關本招股章程及全球發售的資料", "有关本招股章程及全球发售的资料"),
    "directors_and_parties": ("董事、監事及參與全球發售的各方", "董事及參與全球發售的各方"),
    "corporate_information": ("公司資料", "公司资料", "corporate information"),
    "industry_overview": ("行業概覽", "行业概览", "industry overview"),
    "regulatory_overview": ("監管概覽", "监管概览", "regulatory overview"),
    "history_and_corporate_structure": (
        "歷史、發展及公司架構",
        "历史、发展及公司架构",
        "歷史、重組及公司架構",
        "历史、重组及公司架构",
    ),
    "business": ("業務", "业务", "business"),
    "directors_and_management": (
        "董事、監事及高級管理層",
        "董事及高級管理層",
        "董事及高级管理层",
    ),
    "cornerstone_investors": ("基石投資者", "基石投资者"),
    "connected_transactions": (
        "關連交易",
        "关连交易",
        "持續關連交易",
        "持续关连交易",
        "connected transactions",
    ),
    "controlling_shareholders": ("與控股股東的關係", "与控股股东的关系"),
    "share_capital": ("股本", "share capital"),
    "substantial_shareholders": ("主要股東", "主要股东", "substantial shareholders"),
    "financial_information": ("財務資料", "财务资料", "financial information"),
    "future_plans_and_use_of_proceeds": (
        "未來計劃及所得款項用途",
        "未来计划及所得款项用途",
        "future plans and use of proceeds",
    ),
    "underwriting": ("包銷", "包销", "underwriting"),
    "offering_structure": ("全球發售的架構", "全球发售的架构", "structure of the global offering"),
    "application": ("如何申請香港發售股份", "如何申请香港发售股份"),
    "appendix_one": ("附錄一", "附录一", "appendix i", "appendix 1"),
    # Later appendices are retained as boundaries so appendix_one does not
    # accidentally extend to the end of the PDF.
    "appendix_two_a": ("附錄二a", "附录二a", "appendix iia", "appendix 2a"),
    "appendix_two_b": ("附錄二b", "附录二b", "appendix iib", "appendix 2b"),
    "appendix_two": ("附錄二", "附录二", "appendix ii", "appendix 2"),
    "appendix_three": ("附錄三", "附录三", "appendix iii", "appendix 3"),
    "appendix_four": ("附錄四", "附录四", "appendix iv", "appendix 4"),
    "appendix_five": ("附錄五", "附录五", "appendix v", "appendix 5"),
}

_TOC_MARKERS = {"目錄", "目录", "contents"}
_DOT_LEADER_RE = re.compile(
    r"(?P<title>[^.…·•]{2,100}?)\s*(?:[.…·•]{2,}|\s{3,})\s*"
    r"(?P<page>(?:[IVXLCM]+|[A-Z]{1,3})-\d+|\d+|[ivxlcm]+)(?=\s|$)",
    re.I,
)


def _norm(text: str) -> str:
    return re.sub(r"[\s　:：,，、.。·•\-—_()（）]+", "", (text or "")).lower()


_NORMALIZED_ALIASES = {
    section: tuple(_norm(alias) for alias in aliases)
    for section, aliases in CANONICAL_SECTION_ALIASES.items()
}


def canonicalize_section_title(text: str, *, exact: bool = False) -> str | None:
    value = _norm(text)
    if not value:
        return None
    for section, aliases in _NORMALIZED_ALIASES.items():
        for alias in aliases:
            if value == alias:
                return section
            if not exact and (value.startswith(alias) or alias in value):
                # Appendix must remain appendix one, not appendix IIA/IIB/etc.
                if section == "appendix_one" and not re.match(
                    r"^(附錄一|附录一|appendixi(?:$|[^a-z])|appendix1(?:$|[^0-9]))",
                    (text or "").strip(),
                    re.I,
                ):
                    continue
                return section
    return None


@dataclass
class TocEntry:
    title: str
    level: int
    target_page_raw: str
    source_page: int
    canonical_section: str | None = None
    target_page: int | None = None
    confidence: float = 0.6


@dataclass
class SectionSpan:
    canonical_section: str
    display_title: str
    start_page: int
    end_page: int
    level: int = 1
    aliases: list[str] = field(default_factory=list)
    confidence: float = 0.8
    anchor_source: str = "header"
    anchor_pages: list[int] = field(default_factory=list)

    def contains(self, page: int) -> bool:
        return self.start_page <= int(page) <= self.end_page


@dataclass
class SectionMap:
    total_pages: int
    toc_pages: list[int]
    toc_entries: list[TocEntry]
    section_spans: list[SectionSpan]
    page_to_section: dict[int, str]
    page_offset: int | None = None
    version: str = SECTION_MAP_VERSION
    conflicts: list[dict[str, Any]] = field(default_factory=list)

    def section_for_page(self, page: int) -> SectionSpan | None:
        section_id = self.page_to_section.get(int(page))
        if not section_id:
            return None
        return next(
            (span for span in self.section_spans if span.canonical_section == section_id),
            None,
        )

    def span_for(self, canonical_section: str) -> SectionSpan | None:
        return next(
            (span for span in self.section_spans if span.canonical_section == canonical_section),
            None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "total_pages": self.total_pages,
            "toc_pages": self.toc_pages,
            "toc_entries": [asdict(entry) for entry in self.toc_entries],
            "section_spans": [asdict(span) for span in self.section_spans],
            "page_to_section": {str(k): v for k, v in self.page_to_section.items()},
            "page_offset": self.page_offset,
            "conflicts": self.conflicts,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SectionMap":
        return cls(
            version=str(data.get("version") or SECTION_MAP_VERSION),
            total_pages=int(data.get("total_pages") or 0),
            toc_pages=[int(x) for x in data.get("toc_pages") or []],
            toc_entries=[TocEntry(**item) for item in data.get("toc_entries") or []],
            section_spans=[SectionSpan(**item) for item in data.get("section_spans") or []],
            page_to_section={
                int(k): str(v) for k, v in (data.get("page_to_section") or {}).items()
            },
            page_offset=data.get("page_offset"),
            conflicts=list(data.get("conflicts") or []),
        )


def _iter_elements(page: dict[str, Any], categories: Iterable[str]) -> Iterable[dict[str, Any]]:
    allowed = set(categories)
    for element in page.get("elements") or []:
        if element.get("category") in allowed and str(element.get("text") or "").strip():
            yield element


def _detect_toc_pages(pages: list[dict[str, Any]]) -> list[int]:
    found: list[int] = []
    active = False
    for page in pages[:40]:
        page_no = int(page.get("page") or 0)
        labels = [
            _norm(str(element.get("text") or ""))
            for element in _iter_elements(page, ("header", "title"))
        ]
        explicit = any(label in {_norm(x) for x in _TOC_MARKERS} for label in labels)
        body = " ".join(
            str(element.get("text") or "")
            for element in _iter_elements(page, ("text", "table"))
        )
        looks_like_toc = len(_DOT_LEADER_RE.findall(body)) >= 2
        if explicit or looks_like_toc:
            found.append(page_no)
            active = True
        elif active:
            break
    return sorted(set(found))


def _extract_toc_entries(
    pages: list[dict[str, Any]], toc_pages: list[int]
) -> list[TocEntry]:
    entries: list[TocEntry] = []
    wanted = set(toc_pages)
    for page in pages:
        page_no = int(page.get("page") or 0)
        if page_no not in wanted:
            continue
        for element in _iter_elements(page, ("text", "table", "title")):
            text = re.sub(r"\s+", " ", str(element.get("text") or "")).strip()
            for match in _DOT_LEADER_RE.finditer(text):
                title = match.group("title").strip(" .…·•")
                raw_page = match.group("page")
                canonical = canonicalize_section_title(title)
                entries.append(
                    TocEntry(
                        title=title,
                        level=1,
                        target_page_raw=raw_page,
                        source_page=page_no,
                        canonical_section=canonical,
                        confidence=0.8 if canonical else 0.55,
                    )
                )
    return entries


def _collect_main_anchors(
    pages: list[dict[str, Any]], toc_pages: list[int]
) -> tuple[dict[str, list[tuple[int, str, str]]], list[dict[str, Any]]]:
    anchors: dict[str, list[tuple[int, str, str]]] = {}
    conflicts: list[dict[str, Any]] = []
    toc_set = set(toc_pages)

    for page in pages:
        page_no = int(page.get("page") or 0)
        header_hits: list[tuple[str, str, str]] = []
        title_hits: list[tuple[str, str, str]] = []
        for category in ("header", "title"):
            for element in _iter_elements(page, (category,)):
                text = str(element.get("text") or "").strip()
                canonical = canonicalize_section_title(text, exact=True)
                if canonical and not (page_no in toc_set and category == "title"):
                    target = header_hits if category == "header" else title_hits
                    target.append((canonical, text, category))
        # Repeated main-section headers are the authoritative navigation
        # signal. Exact title fallback is only used on pages without one,
        # otherwise a subsection titled “风险因素” inside “概要” becomes a
        # false conflict/main anchor.
        page_hits = header_hits or title_hits
        unique = sorted({hit[0] for hit in page_hits})
        if len(unique) > 1:
            # Multiple headers are common in appendices; appendix_one wins there.
            if "appendix_one" not in unique:
                conflicts.append({"page": page_no, "sections": unique, "type": "multiple_anchors"})
        for hit in page_hits:
            anchors.setdefault(hit[0], []).append((page_no, hit[1], hit[2]))
    return anchors, conflicts


def _build_spans(
    pages: list[dict[str, Any]],
    anchors: dict[str, list[tuple[int, str, str]]],
) -> list[SectionSpan]:
    total_pages = max((int(page.get("page") or 0) for page in pages), default=len(pages))
    starts: list[tuple[int, str, str, str, list[int]]] = []
    for canonical, values in anchors.items():
        header_values = [item for item in values if item[2] == "header"]
        selected = header_values or values
        if not selected:
            continue
        start = min(item[0] for item in selected)
        display = min(selected, key=lambda item: item[0])[1]
        source = "header" if header_values else "title"
        anchor_pages = sorted({item[0] for item in selected})
        starts.append((start, canonical, display, source, anchor_pages))

    starts.sort(key=lambda item: item[0])
    spans: list[SectionSpan] = []
    for idx, (start, canonical, display, source, anchor_pages) in enumerate(starts):
        next_start = starts[idx + 1][0] if idx + 1 < len(starts) else total_pages + 1
        end = max(start, next_start - 1)
        spans.append(
            SectionSpan(
                canonical_section=canonical,
                display_title=display,
                start_page=start,
                end_page=end,
                aliases=list(CANONICAL_SECTION_ALIASES.get(canonical) or (display,)),
                confidence=0.95 if source == "header" and len(anchor_pages) >= 2 else 0.8,
                anchor_source=source,
                anchor_pages=anchor_pages,
            )
        )
    return spans


def _resolve_toc_pages(entries: list[TocEntry], spans: list[SectionSpan]) -> int | None:
    span_by_id = {span.canonical_section: span for span in spans}
    offsets: list[int] = []
    for entry in entries:
        if not entry.canonical_section or not entry.target_page_raw.isdigit():
            continue
        span = span_by_id.get(entry.canonical_section)
        if span:
            offsets.append(span.start_page - int(entry.target_page_raw))
    offset = int(round(statistics.median(offsets))) if offsets else None
    for entry in entries:
        span = span_by_id.get(entry.canonical_section or "")
        if span:
            entry.target_page = span.start_page
            entry.confidence = max(entry.confidence, 0.9)
        elif offset is not None and entry.target_page_raw.isdigit():
            entry.target_page = int(entry.target_page_raw) + offset
    return offset


def build_section_map(pages: list[dict[str, Any]]) -> SectionMap:
    toc_pages = _detect_toc_pages(pages)
    toc_entries = _extract_toc_entries(pages, toc_pages)
    anchors, conflicts = _collect_main_anchors(pages, toc_pages)
    spans = _build_spans(pages, anchors)
    offset = _resolve_toc_pages(toc_entries, spans)
    page_to_section: dict[int, str] = {}
    for span in spans:
        for page in range(span.start_page, span.end_page + 1):
            page_to_section[page] = span.canonical_section
    return SectionMap(
        total_pages=max((int(page.get("page") or 0) for page in pages), default=len(pages)),
        toc_pages=toc_pages,
        toc_entries=toc_entries,
        section_spans=spans,
        page_to_section=page_to_section,
        page_offset=offset,
        conflicts=conflicts,
    )


def build_section_map_from_parse(parse_json_path: str | Path) -> SectionMap:
    with Path(parse_json_path).open(encoding="utf-8") as handle:
        pages = json.load(handle)
    if not isinstance(pages, list):
        raise ValueError(f"Expected list of pages: {parse_json_path}")
    return build_section_map(pages)


def save_section_map(section_map: SectionMap, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(section_map.to_dict(), handle, ensure_ascii=False, indent=2)
    return path
