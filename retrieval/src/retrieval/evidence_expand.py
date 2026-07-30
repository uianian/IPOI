"""Evidence pack expansion + table role tagging for IPO prospectus retrieval.

Policies (agreed):
- Expand: find table OR finish same page; stop at next title; no fill-n page turn.
- table_caption is unreliable — do not use for naming/role.
- table_role: summary | appendix | discussion | other (from headers / cues).
- Row-label channel: match line items inside category=table HTML/text.
- Finance statement recall: appendix-only; cross-page pack for multi-page statements;
  allow statement-like text when parser mis-tagged table as text (e.g. mixue BS p430).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from src.models.prospectus import DocumentChunk

_SKIP_CATS = frozenset({"header", "footer"})
_EXPAND_CATS = frozenset({"text", "table", "table_footnote"})

ROLE_PRIORITY = {
    "appendix": 3,
    "summary": 2,
    "discussion": 1,
    "other": 0,
}

ROLE_SCORE_BONUS = {
    "appendix": 0.06,
    "summary": 0.035,
    "discussion": 0.015,
    "other": 0.0,
}

_CONTINUATION_RE = re.compile(r"[（(]\s*續\s*[)）]|[（(]\s*续\s*[)）]|（续）|\(continued\)", re.I)
_TITLE_CONTINUATION_RE = re.compile(
    r"[—\-–﹣]\s*續|[—\-–﹣]\s*续|"
    r"[（(]\s*續\s*[)）]|[（(]\s*续\s*[)）]|"
    r"（续）|\(continued\)",
    re.I,
)

_PACK_STOP_TITLE_RE = re.compile(
    r"貴公司財務狀況表|公司財務狀況表|貴公司資產負債表|公司資產負債表|"
    r"綜合損益表|综合损益表|"
    r"綜合全面收益表|综合全面收益表|合併綜合收益表|合并综合收益表|"
    r"綜合財務狀況表|综合财务状况表|"
    r"合併權益變動表|合并权益变动表|"
    r"綜合現金流量表|综合现金流量表|"
    r"歷史財務資料附註|历史财务资料附注|"
    r"II\.\s*歷史|II\.\s*历史|"
    r"重大會計政策|重大会计政策|"
    r"^附註\s*$|^附注\s*$",
    re.I,
)

# Do not treat the seed page's own title as a stop signal when continuing.
_STATEMENT_TITLE_BY_TYPE = {
    "income_statement": re.compile(
        r"綜合損益表|综合损益表|合併損益表|合并损益表|損益及其他全面收益表",
        re.I,
    ),
    "balance_sheet": re.compile(
        r"綜合財務狀況表|综合财务状况表|合併財務狀況表|合并财务状况表|資產負債表",
        re.I,
    ),
    "company_balance_sheet": re.compile(
        r"貴公司財務狀況表|公司財務狀況表|貴公司資產負債表|公司資產負債表",
        re.I,
    ),
    "cash_flow": re.compile(
        r"綜合現金流量表|综合现金流量表|合併現金流量表|合并现金流量表",
        re.I,
    ),
}

_CF_BODY_RE = re.compile(
    r"經營活動(?:所得|所用)?現金流量|"
    r"經營\s*[（(]?\s*(?:所用|所得).{0,12}現金|"
    r"投資活動(?:所得|所用)?現金流量|"
    r"融資活動(?:所得|所用)?現金流量",
    re.I,
)
_BS_BODY_RE = re.compile(
    r"非流動資產|非流动资产|流動資產|流动资产|"
    r"總資產|总资产|資產總額|资产总额|資產淨值|资产净值|"
    r"非流動負債|非流动负债|流動負債|流动负债|負債總額|负债总额|權益總額|权益总额",
    re.I,
)
_IS_BODY_RE = re.compile(
    r"銷售成本|销售成本|毛利|年度[／/]?期間內利潤|年內溢利|年内溢利",
    re.I,
)
_COMPANY_ONLY_BS_RE = re.compile(
    r"貴公司財務狀況表|公司財務狀況表|貴公司資產負債表|公司資產負債表",
    re.I,
)
_CONSOLIDATED_BS_RE = re.compile(
    r"綜合財務狀況表|综合财务状况表|合併財務狀況表|合并财务状况表|"
    r"合併資產負債表|合并资产负债表|綜合資產負債表|综合资产负债表",
    re.I,
)
_OCI_TITLE_RE = re.compile(
    r"合併綜合收益表|合并综合收益表|綜合全面收益表|综合全面收益表|"
    r"全面收益表|其他綜合收益表",
    re.I,
)
_TAX_NOTE_RE = re.compile(r"即期稅項|递延稅項|遞延稅項|稅項開支|税项开支|所得稅開支", re.I)
# 损益表后常紧接「全面/綜合收益表」，应视为同表族续表而非停止
_IS_FAMILY_TITLE_RE = re.compile(
    r"綜合全面收益表|综合全面收益表|合併綜合收益表|合并综合收益表|"
    r"全面收益表|綜合收益表|综合收益表",
    re.I,
)


@dataclass
class PageRoleMap:
    """page → table_role inferred from headers / section cues."""

    roles: dict[int, str] = field(default_factory=dict)
    appendix_range: tuple[int, int] | None = None
    summary_pages: list[int] = field(default_factory=list)
    discussion_range: tuple[int, int] | None = None

    def role_of(self, page: int) -> str:
        return self.roles.get(page, "other")


@dataclass
class ExpandResult:
    anchor: DocumentChunk
    members: list[DocumentChunk]
    stop_reason: str
    found_table: DocumentChunk | None = None

    @property
    def primary(self) -> DocumentChunk:
        return self.found_table or self.anchor


@dataclass
class StatementPack:
    """One logical statement possibly spanning multiple pages/chunks."""

    seed: DocumentChunk
    members: list[DocumentChunk]
    stop_reason: str

    @property
    def pages(self) -> list[int]:
        return sorted({int(m.page_number) for m in self.members})

    @property
    def primary(self) -> DocumentChunk:
        return self.members[0] if self.members else self.seed

    def merged_content(self, max_chars: int = 50000) -> str:
        parts: list[str] = []
        for m in self.members:
            if _cat(m) not in ("table", "text"):
                continue
            parts.append(m.content or "")
        blob = "\n\n<!-- page_break -->\n\n".join(parts)
        return blob[:max_chars]


def _cat(chunk: DocumentChunk) -> str:
    return str((chunk.metadata or {}).get("category") or chunk.chunk_type or "text")


def _elem_index(chunk: DocumentChunk) -> int:
    meta = chunk.metadata or {}
    if "elem_index" in meta:
        return int(meta["elem_index"])
    return int(chunk.paragraph_index or 0)


def _norm_header(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def build_page_role_map(chunks: Iterable[DocumentChunk]) -> PageRoleMap:
    """Infer summary / discussion / appendix page roles from indexed chunks."""
    headers: dict[int, list[str]] = defaultdict(list)
    titles: dict[int, list[str]] = defaultdict(list)
    texts: dict[int, list[str]] = defaultdict(list)
    pages: set[int] = set()

    for c in chunks:
        page = int(c.page_number)
        pages.add(page)
        cat = _cat(c)
        content = c.content or ""
        if cat == "header":
            headers[page].append(content)
        elif cat == "title":
            titles[page].append(content)
        elif cat == "text":
            texts[page].append(content[:200])

    roles: dict[int, str] = {}
    appendix_pages: list[int] = []
    summary_pages: list[int] = []
    discussion_pages: list[int] = []

    for page in sorted(pages):
        h = _norm_header("".join(headers.get(page, [])))
        title_blob = "".join(titles.get(page, []))
        text_blob = "".join(texts.get(page, []))

        if "附錄一" in h or "附录一" in h:
            roles[page] = "appendix"
            appendix_pages.append(page)
            continue

        if "財務資料" in h or "财务资料" in h:
            if "備考" in h or "备考" in h:
                roles[page] = "other"
            else:
                roles[page] = "discussion"
                discussion_pages.append(page)
            continue

        if (
            "歷史財務資料概要" in title_blob
            or "历史财务资料概要" in title_blob
            or h in ("概要",)
            or ("概要" in h and page < 80)
        ):
            roles[page] = "summary"
            summary_pages.append(page)
            continue

        if ("下表" in text_blob or "下表載列" in text_blob) and "概要" in text_blob:
            roles[page] = "summary"
            summary_pages.append(page)
            continue

        roles[page] = "other"

    appendix_range = None
    if appendix_pages:
        appendix_range = (min(appendix_pages), max(appendix_pages))
    discussion_range = None
    if discussion_pages:
        discussion_range = (min(discussion_pages), max(discussion_pages))

    return PageRoleMap(
        roles=roles,
        appendix_range=appendix_range,
        summary_pages=sorted(set(summary_pages)),
        discussion_range=discussion_range,
    )


def build_page_index(
    chunks: list[DocumentChunk],
) -> dict[int, list[DocumentChunk]]:
    by_page: dict[int, list[DocumentChunk]] = defaultdict(list)
    for c in chunks:
        by_page[int(c.page_number)].append(c)
    for page in by_page:
        by_page[page].sort(key=_elem_index)
    return dict(by_page)


def table_has_row_label(content: str, label: str) -> bool:
    if not content or not label:
        return False
    pat = re.compile(
        rf"<td[^>]*>\s*{re.escape(label)}\s*</td>",
        re.IGNORECASE,
    )
    if pat.search(content):
        return True
    pat2 = re.compile(
        rf"<td[^>]*>\s*{re.escape(label)}\s*[（(0-9注註\*]*\s*</td>",
        re.IGNORECASE,
    )
    if pat2.search(content):
        return True
    if re.search(rf"(?:^|\n)\s*{re.escape(label)}\s*(?:\t|\s{{2,}}|$)", content):
        return True
    return False


def matched_row_labels(content: str, row_labels: list[str]) -> list[str]:
    if not content or not row_labels:
        return []
    out: list[str] = []
    for lb in row_labels:
        if not lb:
            continue
        if table_has_row_label(content, lb) or lb in content:
            out.append(lb)
    return out


def statement_body_score(content: str, row_labels: list[str]) -> tuple[float, list[str]]:
    matched = matched_row_labels(content, row_labels)
    score = float(len(matched))
    if "於12月31日" in content or "截至12月31日" in content or "于12月31日" in content:
        score += 0.5
    if "非流動資產" in content or "非流动资产" in content or "流動資產" in content:
        score += 0.5
    if "經營活動" in content and ("投資活動" in content or "融资活動" in content or "融資活動" in content):
        score += 0.5
    return score, matched


def infer_statement_kind(content: str, page_title_blob: str = "") -> str:
    """Classify statement-like body: income_statement | balance_sheet | cash_flow | note | unknown."""
    titles = page_title_blob or ""
    blob = f"{titles}\n{content or ''}"
    # Title-first disambiguation (Xiaomi: 合併綜合收益表 ≠ 資產負債表)
    if _OCI_TITLE_RE.search(titles) and not _CONSOLIDATED_BS_RE.search(titles):
        return "income_statement"
    if _CF_BODY_RE.search(blob) or (
        "經營活動現金流量" in blob and ("投資活動" in blob or "融資活動" in blob)
    ):
        return "cash_flow"
    if _IS_BODY_RE.search(blob) and (
        "收入" in blob or "收益" in blob or "營業額" in blob or "营业额" in blob
    ):
        # OCI-only pages may lack 銷售成本; title already handled above
        return "income_statement"
    if _COMPANY_ONLY_BS_RE.search(titles):
        return "company_balance_sheet"
    # 合并 BS 标题（含「續」）优先：续页可能只有负债/权益半表
    if _CONSOLIDATED_BS_RE.search(titles) and (
        _BS_BODY_RE.search(blob) or "負債" in blob or "权益" in blob or "權益" in blob or "資產" in blob
    ):
        return "balance_sheet"
    if _BS_BODY_RE.search(blob) and (
        "總資產" in blob
        or "总资产" in blob
        or "資產總額" in blob
        or "资产总额" in blob
        or "資產淨值" in blob
        or "资产净值" in blob
        or "權益總額" in blob
        or "負債總額" in blob
    ):
        return "balance_sheet"
    if _TAX_NOTE_RE.search(blob):
        return "note"
    return "unknown"


def statement_kind_compatible(table_type: str, kind: str) -> bool:
    """Whether inferred kind may serve as evidence for the requested table_type."""
    if not table_type:
        return True
    if kind in ("", "unknown"):
        return True
    if table_type == "balance_sheet":
        # 合并/综合表；贵公司单体表走 company_balance_sheet / TBL_BS_COMPANY
        return kind == "balance_sheet"
    if table_type == "company_balance_sheet":
        return kind == "company_balance_sheet"
    if table_type == "cash_flow":
        return kind == "cash_flow"
    if table_type == "income_statement":
        return kind == "income_statement"
    return True


def page_title_blob(page_chunks: list[DocumentChunk]) -> str:
    return " ".join(
        (c.content or "") for c in page_chunks if _cat(c) == "title"
    )


def must_have_groups_ok(content: str, groups: list[list[str]] | None) -> bool:
    """Each group needs ≥1 label hit (OR within group, AND across groups)."""
    if not groups:
        return True
    blob = content or ""
    for group in groups:
        labels = [str(x) for x in group if x]
        if not labels:
            continue
        if not matched_row_labels(blob, labels):
            return False
    return True


def consolidated_title_bonus(page_title: str, table_type: str) -> float:
    if table_type != "balance_sheet":
        return 0.0
    if _CONSOLIDATED_BS_RE.search(page_title or ""):
        return 0.08
    if _COMPANY_ONLY_BS_RE.search(page_title or ""):
        return -0.12
    return 0.0


def expand_anchor(
    anchor: DocumentChunk,
    page_index: dict[int, list[DocumentChunk]],
    *,
    allow_continuation: bool = True,
    row_labels: list[str] | None = None,
    allow_text_as_table: bool = False,
    min_row_label_hits: int = 0,
) -> ExpandResult:
    """Same-page expand; optionally accept statement-like text as body."""
    cat = _cat(anchor)
    page = int(anchor.page_number)
    page_chunks = page_index.get(page) or []
    labels = list(row_labels or [])

    def _accept_text_as_body(c: DocumentChunk) -> bool:
        if not allow_text_as_table or _cat(c) != "text":
            return False
        content = c.content or ""
        if len(content) < 80:
            return False
        _score, matched = statement_body_score(content, labels)
        need = max(min_row_label_hits, 2) if labels else 3
        return len(matched) >= need

    if cat == "table":
        members = [anchor]
        start = None
        for i, c in enumerate(page_chunks):
            if c.chunk_id == anchor.chunk_id:
                start = i
                break
        if start is not None:
            for c in page_chunks[start + 1 :]:
                ccat = _cat(c)
                if ccat in _SKIP_CATS:
                    continue
                if ccat in ("title", "table"):
                    break
                if ccat == "table_footnote":
                    members.append(c)
                elif ccat == "text":
                    break
        return ExpandResult(
            anchor=anchor,
            members=members,
            stop_reason="already_table",
            found_table=anchor,
        )

    if _accept_text_as_body(anchor):
        return ExpandResult(
            anchor=anchor,
            members=[anchor],
            stop_reason="text_as_statement",
            found_table=anchor,
        )

    start_idx = 0
    for i, c in enumerate(page_chunks):
        if c.chunk_id == anchor.chunk_id:
            start_idx = i + 1
            break

    members: list[DocumentChunk] = []
    found_table: DocumentChunk | None = None
    stop_reason = "same_page_exhausted"

    for c in page_chunks[start_idx:]:
        ccat = _cat(c)
        if ccat in _SKIP_CATS:
            continue
        if ccat == "title":
            stop_reason = "next_title"
            break
        if ccat not in _EXPAND_CATS:
            continue
        members.append(c)
        if ccat == "table":
            found_table = c
            stop_reason = "found_table"
            break
        if _accept_text_as_body(c):
            found_table = c
            stop_reason = "text_as_statement"
            break

    if (
        allow_continuation
        and found_table is None
        and stop_reason == "same_page_exhausted"
        and members
    ):
        last = members[-1]
        last_text = last.content or ""
        if _CONTINUATION_RE.search(last_text) or _cat(last) == "table_footnote":
            next_page = page_index.get(page + 1) or []
            for c in next_page:
                ccat = _cat(c)
                if ccat in _SKIP_CATS:
                    continue
                if ccat == "title":
                    break
                if ccat == "table":
                    members.append(c)
                    found_table = c
                    stop_reason = "found_table_continuation"
                    break
                if _accept_text_as_body(c):
                    members.append(c)
                    found_table = c
                    stop_reason = "text_as_statement_continuation"
                    break
                if ccat == "text":
                    if _CONTINUATION_RE.search(c.content or ""):
                        members.append(c)
                        continue
                    break

    if found_table is None and not members:
        stop_reason = "narrative_only" if cat in ("title", "text") else stop_reason

    if found_table is None and members and all(_cat(m) == "text" for m in members):
        if cat == "title":
            stop_reason = "narrative_only"

    return ExpandResult(
        anchor=anchor,
        members=members,
        stop_reason=stop_reason,
        found_table=found_table,
    )


def collect_cross_page_pack(
    seed: DocumentChunk,
    page_index: dict[int, list[DocumentChunk]],
    role_map: PageRoleMap | None = None,
    *,
    max_pages: int = 4,
    appendix_only: bool = True,
    row_labels: list[str] | None = None,
    min_row_label_hits: int = 0,
    table_type: str = "",
    allowed_page_range: tuple[int, int] | None = None,
) -> StatementPack:
    """Collect seed + following consecutive pages of the same statement."""
    labels = list(row_labels or [])
    seed_page = int(seed.page_number)
    members: list[DocumentChunk] = [seed]
    stop_reason = "pack_done"
    own_title_re = _STATEMENT_TITLE_BY_TYPE.get(table_type)

    def _page_has_stop_title(page: int) -> bool:
        for c in page_index.get(page) or []:
            if _cat(c) != "title":
                continue
            text = c.content or ""
            if table_type == "income_statement" and _IS_FAMILY_TITLE_RE.search(text):
                continue
            # 同表「—續」页不算新表
            if own_title_re and own_title_re.search(text) and _TITLE_CONTINUATION_RE.search(text):
                continue
            if not _PACK_STOP_TITLE_RE.search(text):
                # 其他主表标题（含合併資產負債表新开篇，无續）也应停止
                if own_title_re and own_title_re.search(text) and page != seed_page:
                    if not _TITLE_CONTINUATION_RE.search(text):
                        return True
                continue
            if own_title_re and own_title_re.search(text) and page == seed_page:
                continue
            return True
        return False

    def _page_body_chunks(page: int) -> list[DocumentChunk]:
        out: list[DocumentChunk] = []
        titles = page_title_blob(page_index.get(page) or [])
        for c in page_index.get(page) or []:
            ccat = _cat(c)
            content = c.content or ""
            if ccat == "table":
                kind = infer_statement_kind(content, titles)
                if table_type and not statement_kind_compatible(table_type, kind) and kind not in (
                    "unknown",
                    "",
                ):
                    continue
                out.append(c)
            elif ccat == "text" and labels:
                _score, matched = statement_body_score(content, labels)
                need = max(min_row_label_hits, 1)
                if len(matched) >= need or _score >= 2.0:
                    kind = infer_statement_kind(content, titles)
                    if table_type and not statement_kind_compatible(table_type, kind) and kind not in (
                        "unknown",
                        "",
                    ):
                        continue
                    out.append(c)
        return out

    for offset in range(1, max_pages):
        page = seed_page + offset
        if allowed_page_range is not None and not (
            allowed_page_range[0] <= page <= allowed_page_range[1]
        ):
            stop_reason = "left_section_span"
            break
        if role_map is not None and appendix_only:
            if role_map.role_of(page) != "appendix":
                stop_reason = "left_appendix"
                break
        if _page_has_stop_title(page):
            stop_reason = "stop_title"
            break
        bodies = _page_body_chunks(page)
        if not bodies:
            stop_reason = "no_continuation_body"
            break
        members.extend(bodies)
        stop_reason = f"continued_to_p{page}"

    return StatementPack(seed=seed, members=members, stop_reason=stop_reason)


def row_label_search(
    chunks: list[DocumentChunk],
    row_labels: list[str],
    *,
    top_k: int = 20,
    role_map: PageRoleMap | None = None,
    appendix_only: bool = False,
    allow_text: bool = False,
    page_range: tuple[int, int] | None = None,
) -> list[tuple[DocumentChunk, float, list[str]]]:
    """Grep table (and optionally text) chunks for financial line-item labels."""
    if not row_labels:
        return []
    labels = [str(x) for x in row_labels if x]
    scored: list[tuple[DocumentChunk, float, list[str]]] = []
    for c in chunks:
        if page_range is not None and not (
            page_range[0] <= int(c.page_number) <= page_range[1]
        ):
            continue
        cat = _cat(c)
        if cat != "table" and not (allow_text and cat == "text"):
            continue
        if appendix_only and role_map is not None:
            if role_map.role_of(int(c.page_number)) != "appendix":
                continue
        content = c.content or ""
        score, matched = statement_body_score(content, labels)
        if not matched:
            continue
        if role_map is not None:
            score += ROLE_SCORE_BONUS.get(role_map.role_of(int(c.page_number)), 0.0) * 10
        if "截至" in content or "12月31日" in content or "附註" in content or "附注" in content:
            score += 0.5
        scored.append((c, score, matched))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def role_score_bonus(role: str) -> float:
    return ROLE_SCORE_BONUS.get(role, 0.0)


def short_title_penalty(chunk: DocumentChunk, expanded: ExpandResult | None) -> float:
    if _cat(chunk) != "title":
        return 0.0
    if expanded and expanded.found_table is not None:
        return 0.0
    text = (chunk.content or "").strip()
    if len(text) <= 20 and not re.search(r"\d", text):
        return -0.025
    return -0.01
