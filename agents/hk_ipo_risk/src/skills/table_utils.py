from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any


_NUM_RE = re.compile(
    r"^\(?-?[\d,]+(?:\.\d+)?\)?$|^–$|^-$|^—$|^N/?A$",
    re.IGNORECASE,
)

# 行名上下文黑名单：命中则该行不得作为对应指标（明文/HTML 共用）
FIELD_LINE_REJECT: dict[str, tuple[str, ...]] = {
    "REV": ("其他收入", "其他收益", "利息收入", "公允價值收益", "公允价值收益", "政府補助", "政府补助"),
    "TOTAL_ASSETS": ("減", "减", "減去", "减去"),
    "TOTAL_LIAB": ("流動負債總額", "流动负债总额", "非流動負債總額", "非流动负债总额"),
    "NET_LOSS": ("每股", "減值虧損", "减值亏损", "其他收益及虧損", "其他收益及亏损", "出售"),
    "CFO": ("投資活動", "融资活動", "融資活動", "融資成本", "融资成本"),
}


def parse_number(cell: str) -> float | None:
    s = (cell or "").strip().replace(",", "").replace(" ", "")
    if not s or s in {"–", "-", "—", "—", "N/A", "n/a", "NA"}:
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    try:
        val = float(s)
    except ValueError:
        return None
    return -val if neg else val


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] = []
        self._cell: list[str] = []
        self._in_td = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("td", "th"):
            self._in_td = True
            self._cell = []
        elif tag == "tr":
            self._row = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._in_td:
            self._in_td = False
            self._row.append("".join(self._cell).strip())
        elif tag == "tr":
            if self._row:
                self.rows.append(self._row)
            self._row = []

    def handle_data(self, data: str) -> None:
        if self._in_td:
            self._cell.append(data)


def html_table_to_rows(html: str) -> list[list[str]]:
    if "<table" not in html.lower():
        # plaintext fallback: split lines loosely
        return [[c.strip() for c in line.split()] for line in html.splitlines() if line.strip()]
    parser = _TableParser()
    parser.feed(html)
    return parser.rows


_INTERIM_HINT_RE = re.compile(
    r"個月|个月|中期|interim|止\s*\d+\s*個?月|止\s*\d+\s*个?月",
    re.I,
)
_YE_HINT_RE = re.compile(r"止年度|12\s*月\s*31|年末|年結", re.I)


def _cell_interim_hint(text: str) -> bool:
    """中期列提示；「截至12月31日止年度」等全年列不算中期。"""
    if not text:
        return False
    if _YE_HINT_RE.search(text):
        return False
    return bool(_INTERIM_HINT_RE.search(text))


def _mark_track_record_interim_tail(years: list[str]) -> list[str]:
    """HK IPO 常见列：两年完整年度 + 两段中期（如 2023,2024,2024_i1,2025）。

    末列若为「仅出现一次」的下一自然年、且前面已有中期列，则标为 *_i1，
    避免把八个月 stub 当成完整年度参与门控。
    """
    if len(years) < 3 or not any("_i" in y for y in years):
        return years
    out = list(years)
    last = out[-1]
    if not str(last).isdigit():
        return out
    base_counts: dict[str, int] = {}
    for y in out[:-1]:
        b = str(y).split("_", 1)[0]
        base_counts[b] = base_counts.get(b, 0) + 1
    if last in base_counts:
        return out
    out[-1] = f"{last}_i1"
    return out


def _mark_mixed_ye_interim_columns(years: list[str], header_blob: str) -> list[str]:
    """资产负债表常见：於12月31日 | 於12月31日 | 於8月31日 → 末列中期。

    年份行本身可能只有 2023/2024/2025，日期提示在相邻表头行。
    """
    if len(years) < 3:
        return years
    has_ye = bool(re.search(r"12\s*月\s*31|止年度|年末", header_blob))
    has_interim = bool(
        re.search(r"(?:6|8|9)\s*月\s*30?1?|個月|个月|中期|止\s*八", header_blob)
    )
    if not (has_ye and has_interim):
        return years
    out = list(years)
    last = out[-1]
    if str(last).isdigit():
        out[-1] = f"{last}_i1"
    return out


def _years_from_found(found: list[tuple[str, bool]], header_blob: str) -> list[str]:
    out: list[str] = []
    seen: dict[str, int] = {}
    for y, interim_hint in found:
        if y not in seen:
            seen[y] = 0
            if interim_hint:
                seen[y] = 1
                out.append(f"{y}_i1")
            else:
                out.append(y)
        else:
            seen[y] += 1
            out.append(f"{y}_i{seen[y]}")
    out = _mark_track_record_interim_tail(out)
    return _mark_mixed_ye_interim_columns(out, header_blob)


_UNIT_ONLY_RE = re.compile(
    r"^(人民幣|人民币|港元|千元|万元|千港元|百萬|百万).*$|^元$"
)

_CN_YEAR_DIGIT = {
    "零": "0",
    "〇": "0",
    "○": "0",
    "一": "1",
    "二": "2",
    "三": "3",
    "四": "4",
    "五": "5",
    "六": "6",
    "七": "7",
    "八": "8",
    "九": "9",
}
_CN_YEAR_RE = re.compile(r"二[零〇○一二三四五六七八九]{3}")
_ARABIC_YEAR_RE = re.compile(r"(20\d{2})")


def chinese_year_to_arabic(text: str) -> str | None:
    """二零一八 → 2018；非四位年份返回 None。"""
    m = _CN_YEAR_RE.search(text or "")
    if not m:
        return None
    digits = "".join(_CN_YEAR_DIGIT.get(ch, "") for ch in m.group(0))
    if len(digits) == 4 and digits.startswith("20"):
        return digits
    return None


def _years_in_cell(text: str) -> list[tuple[str, bool]]:
    """Arabic 20xx first; else 中文数字年份（健世/榮昌表头）。"""
    found: list[tuple[str, bool]] = []
    for m in _ARABIC_YEAR_RE.finditer(text or ""):
        found.append((m.group(1), _cell_interim_hint(text)))
    if found:
        return found
    cy = chinese_year_to_arabic(text or "")
    if cy:
        found.append((cy, _cell_interim_hint(text)))
    return found


def extract_year_headers(rows: list[list[str]]) -> list[str]:
    """Keep column order; duplicate years / interim hints get _i suffix.

    - 单行 ≥2 个年份即可（港股两年往绩常见）
    - 若单行不足，按列号跨行聚合（「2022年」与「人民幣千元」分行）
    - 支持「二零二零年人民幣千元」
    """
    header_blob = " ".join(c for row in rows[:8] for c in row)
    # 1) 同行多列年份
    for row in rows[:8]:
        found: list[tuple[str, bool]] = []
        for cell in row:
            found.extend(_years_in_cell(cell or ""))
        if len(found) >= 2:
            return _years_from_found(found, header_blob)

    # 2) 跨行按列聚合：忽略纯单位行，按列下标收年
    col_year: dict[int, tuple[str, bool]] = {}
    for row in rows[:8]:
        for col_i, cell in enumerate(row):
            text = (cell or "").strip()
            if not text or _UNIT_ONLY_RE.match(text):
                continue
            hits = _years_in_cell(text)
            if not hits:
                continue
            y, interim = hits[0]
            prev = col_year.get(col_i)
            if prev is None or (interim and not prev[1]):
                col_year[col_i] = (y, interim)
    if len(col_year) >= 2:
        found = [col_year[i] for i in sorted(col_year)]
        return _years_from_found(found, header_blob)
    # 3) 文本表把「2023年」「2024年」拆成多行同一列（映恩等）
    stacked: list[tuple[str, bool]] = []
    for row in rows[:12]:
        blob = " ".join(c for c in row if c)
        if not blob.strip() or _UNIT_ONLY_RE.match(blob.strip()):
            continue
        if re.search(r"\d{1,3}(?:,\d{3})+", blob):
            continue
        hits = _years_in_cell(blob)
        if hits:
            stacked.extend(hits)
    if len({y for y, _ in stacked}) >= 2:
        return _years_from_found(stacked, header_blob)
    return []


def line_rejected_for_field(line: str, field: str | None) -> bool:
    if not field:
        return False
    rejects = FIELD_LINE_REJECT.get(field) or ()
    s = line or ""
    return any(tok in s for tok in rejects)


def _normalize_row_label_cell(cell: str) -> str:
    """Strip leaders/ellipsis used in prospectus table stubs (．．．．)."""
    s = (cell or "").strip()
    s = re.sub(r"[\.．…⋯]+$", "", s).strip()
    return s


_TRAD_FOLD = str.maketrans(
    {
        "稅": "税",
        "經": "经",
        "營": "营",
        "現": "现",
        "額": "额",
        "損": "损",
        "虧": "亏",
        "產": "产",
        "內": "内",
        "開": "开",
        "應": "应",
        "佔": "占",
        "總": "总",
        "潤": "润",
        "淨": "净",
        "動": "动",
        "餘": "余",
        "與": "与",
        "為": "为",
        "從": "从",
        "會": "会",
        "計": "计",
        "綜": "综",
        "負": "负",
        "債": "债",
        "資": "资",
        "幣": "币",
        "權": "权",
        "結": "结",
        "業": "业",
        "務": "务",
        "報": "报",
        "項": "项",
        "費": "费",
        "減": "减",
        "備": "备",
        "關": "关",
        "聯": "联",
        "東": "东",
        "發": "发",
        "變": "变",
        "購": "购",
        "貨": "货",
        "銷": "销",
        "術": "术",
        "際": "际",
        "數": "数",
        "據": "据",
        "億": "亿",
        "萬": "万",
        "點": "点",
        "後": "后",
        "於": "于",
        "並": "并",
        "將": "将",
        "屬": "属",
        "對": "对",
        "調": "调",
        "攤": "摊",
        "撥": "拨",
    }
)


def _fold_label(text: str) -> str:
    """Unify punctuation/spaces/glyphs so 溢利 (虧損) matches 溢利（虧損）."""
    s = (text or "").strip().translate(_TRAD_FOLD)
    s = s.replace("（", "(").replace("）", ")")
    s = s.replace("／", "/").replace(" ", "").replace("　", "")
    return s


# 先瑞達「年／期內溢利 (虧損) 及全面收益 (開支) 總額」；開拓「除所得稅前虧損／應佔年內虧損」
_NET_LOSS_ROW_RE = re.compile(
    r"(年/?期内?|期内|年内).{0,8}(溢利|利润|亏损)"
    r"|除(所得税?)?前.{0,6}(溢利|亏损)"
    r"|税前(溢利|亏损)"
    r"|应占.{0,16}(年内|期内)(亏损|溢利)"
    r"|全面(亏损|开支|收益).{0,6}总额",
    re.I,
)
_CFO_ROW_RE = re.compile(
    r"经营活动(所得|所用|所产生|产生).{0,12}现金(流量)?净额"
    r"|经营所用现金净额"
    r"|经营所得/?.{0,6}现金净额",
    re.I,
)


def _row_label_score(first_cell: str, labels: list[str], *, field: str | None = None) -> int:
    """Higher is better. Prefer exact / prefix match to avoid 其他收入 matching 收入."""
    cell = _normalize_row_label_cell(first_cell)
    if not cell:
        return 0
    if line_rejected_for_field(cell, field):
        return 0
    folded_cell = _fold_label(cell)
    best = 0
    for lab in labels:
        if not lab:
            continue
        folded_lab = _fold_label(lab)
        if cell == lab or folded_cell == folded_lab:
            best = max(best, 100)
        elif lab == cell.replace(" ", ""):
            best = max(best, 90)
        elif cell.startswith(lab) and len(cell) <= len(lab) + 4:
            # 允许「收入。」等短后缀；禁止「收入」匹配「其他收入及收益」
            best = max(best, 80)
        elif folded_cell.startswith(folded_lab) and len(folded_cell) <= len(folded_lab) + 8:
            best = max(best, 80)
        elif cell.startswith(lab) or folded_cell.startswith(folded_lab):
            best = max(best, 50)
        # 禁止 lab 为 cell 的真子串（如 收入 ⊂ 其他收入及收益、資產總值 ⊂ 資產總值減…）
        elif lab in cell and not cell.startswith(lab):
            continue
    if field == "NET_LOSS":
        if best < 50 and _NET_LOSS_ROW_RE.search(folded_cell):
            best = 75
        # 税前是回退口径：有「年內/期內」底行时不得压过
        pretax_only = bool(
            re.search(r"除(所得税?)?前|税前", folded_cell)
        ) and not re.search(r"年/?期内?|期内|年内|应占", folded_cell)
        if pretax_only and best:
            best = min(best, 62)
        if re.search(
            r"(年/?期内?|期内|年内).{0,16}(溢利|利润|亏损)|全面(亏损|开支).{0,8}总额",
            folded_cell,
        ):
            best = max(best, 90)
    if best < 50 and field == "CFO" and _CFO_ROW_RE.search(folded_cell):
        best = 75
    return best


_LABEL_CONTINUATION = re.compile(
    r"^(現金流量淨額|现金净额|現金淨額|的現金淨額|净额|淨額)$"
)


def _row_numeric_cells(
    row: list[str],
    *,
    n_years: int | None = None,
) -> list[float | None]:
    """Extract numeric cells after the label column.

    When n_years is known, keep trailing data columns aligned (do not drop
    mid-row blanks that would shift year zip). Footnote indices still skipped.
    """
    cells = row[1:]
    if n_years and n_years > 0 and len(cells) >= n_years:
        # Prefer rightmost n_years cells (label | 附註 | y1 | y2)
        slice_cells = cells[-n_years:]
        out: list[float | None] = []
        for c in slice_cells:
            s = (c or "").strip()
            if not s or s in {"–", "-", "—", "—", "N/A", "n/a", "NA"}:
                out.append(None)
                continue
            if s.isdigit() and len(s) <= 2:
                out.append(None)
                continue
            out.append(parse_number(c))
        return out

    numeric_cells: list[float | None] = []
    for c in cells:
        s = (c or "").strip()
        # skip blank / footnote index; do not shift year alignment
        if not s or (s.isdigit() and len(s) <= 2):
            continue
        if s in {"–", "-", "—", "—", "N/A", "n/a", "NA"}:
            numeric_cells.append(None)
            continue
        n = parse_number(c)
        if n is not None:
            numeric_cells.append(n)
    return numeric_cells


def find_row_values(
    rows: list[list[str]],
    labels: list[str],
    years: list[str],
    *,
    field: str | None = None,
) -> dict[str, float | None]:
    """Match first column against labels; map numeric cells to years.

    支持拆行标签：如「經營活動所得／（所用）」下一行才是「現金流量淨額」+ 数值。
    """
    best_score = 0
    best_vals: dict[str, float | None] = {}
    n_years = len(years) if years else None
    for idx, row in enumerate(rows):
        if not row:
            continue
        first = (row[0] or "").strip()
        score = _row_label_score(first, labels, field=field)
        # 映恩等：行名被拆成「應佔年內」+「全面虧損總額」两格
        if score < 90 and len(row) > 1:
            second = (row[1] or "").strip()
            if second and parse_number(second) is None and not _NUM_RE.match(second):
                joined = first + second
                score = max(score, _row_label_score(joined, labels, field=field))
        if score < 50:
            continue
        numeric_cells = _row_numeric_cells(row, n_years=n_years)
        # 标签命中但本行无数字：尝试下一行续行标签
        if (not numeric_cells or all(v is None for v in numeric_cells)) and idx + 1 < len(
            rows
        ):
            nxt = rows[idx + 1]
            nxt_first = _normalize_row_label_cell((nxt[0] if nxt else "") or "")
            if _LABEL_CONTINUATION.match(nxt_first) or "淨額" in nxt_first or "净额" in nxt_first:
                numeric_cells = _row_numeric_cells(nxt, n_years=n_years)
                score = max(score, 85)
        if not numeric_cells or all(v is None for v in numeric_cells):
            continue
        # 年份数与数值列明显不符时不硬套，避免错年
        if years and abs(len(numeric_cells) - len(years)) > 1 and len(years) >= 2:
            if len(numeric_cells) < len(years):
                # 仍按较短 zip，但不扩展假年
                pass
            elif len(numeric_cells) > len(years) + 1:
                continue
        use_years = list(years) if years else [f"p{i}" for i in range(len(numeric_cells))]
        out: dict[str, float | None] = {}
        for i, y in enumerate(use_years):
            out[y] = numeric_cells[i] if i < len(numeric_cells) else None
        if score > best_score:
            best_score = score
            best_vals = out
    return best_vals


def _looks_empty_num(c: str) -> bool:
    s = (c or "").strip()
    return s in {"", "–", "-", "—", "—"}


def extract_metrics_from_table_html(
    html: str,
    field_label_map: dict[str, list[str]],
) -> dict[str, dict[str, float | None]]:
    rows = html_table_to_rows(html)
    years = extract_year_headers(rows)
    if not years:
        # fallback generic period keys
        years = [f"col{i}" for i in range(5)]
    metrics: dict[str, dict[str, float | None]] = {}
    for field, labels in field_label_map.items():
        vals = find_row_values(rows, labels, years, field=field)
        if vals:
            metrics[field] = vals
    return {"_years": {y: None for y in years}, **metrics}  # type: ignore[dict-item]


def _parse_nums_after(text: str) -> list[float]:
    nums = re.findall(r"\(?-?[\d,]+(?:\.\d+)?\)?", text)
    parsed: list[float] = []
    for n in nums:
        if n.isdigit() and len(n) <= 2:
            continue
        p = parse_number(n)
        if p is not None:
            parsed.append(p)
    return parsed


def plaintext_row_search(
    text: str,
    labels: list[str],
    *,
    field: str | None = None,
    min_nums: int = 2,
) -> dict[str, Any]:
    """When HTML missing, grab a line containing label + nearby numbers.

    与 HTML 路径一致：拒绝黑名单行；要求 label 在行首附近且不是长行名的真子串。
    默认 min_nums=2（港股两年往绩）。
    """
    labels_sorted = sorted((lab for lab in labels if lab), key=len, reverse=True)
    best: dict[str, Any] = {}
    best_score = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line_rejected_for_field(line, field):
            continue
        # 取行首片段作「行名」打分（附录 text 表常为「行名 附注 数值…」）
        head = re.split(r"\s{2,}|\t|(?=\d)", line, maxsplit=1)[0].strip()
        if not head:
            head = line[:40]
        score = _row_label_score(head, labels_sorted, field=field)
        if score < 50:
            # 兼容「行名」后紧跟数字、head 切得过短：用整行再试一次精确前缀
            score = _row_label_score(line[:48], labels_sorted, field=field)
        if score < 50:
            continue
        # 数值取自第一个命中 label 之后
        after = line
        for lab in labels_sorted:
            if line.startswith(lab) or head.startswith(lab):
                idx = line.find(lab)
                after = line[idx + len(lab) :]
                break
        parsed = _parse_nums_after(after)
        if len(parsed) < min_nums:
            continue
        mag = abs(parsed[0]) if parsed else 0
        total = score * 10 + len(parsed) + min(mag / 1e6, 50)
        if total > best_score:
            best_score = total
            best = {"line": line[:240], "numbers": parsed, "match_score": score}
    return best
