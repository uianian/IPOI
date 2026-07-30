"""扫描 output/samples_batch，建立 ticker / sha256 / 关键词 → 解析产物目录。"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from service.config import PDF_DIR, SAMPLES_DIR

logger = logging.getLogger(__name__)

_TICKER_RE = re.compile(r"^(\d{5})")


@dataclass(frozen=True)
class SampleEntry:
    key: str
    parse_dir: Path
    ticker: Optional[str]
    keywords: tuple[str, ...]
    pdf_path: Optional[Path]
    sha256: Optional[str]
    page_count: int


def file_sha256(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def _read_page_count(parse_dir: Path) -> int:
    summary = parse_dir / "parse_summary.json"
    if not summary.is_file():
        return 0
    try:
        data = json.loads(summary.read_text(encoding="utf-8"))
        return int(data.get("total_pages") or 0)
    except Exception:
        return 0


def _keywords_from_stem(stem: str) -> tuple[str, ...]:
    parts = re.split(r"[_\-－]", stem)
    kws: list[str] = []
    for p in parts:
        p = p.strip()
        if not p or re.fullmatch(r"\d{5}", p) or re.fullmatch(r"\d{2}-\d{2}-\d{4}", p):
            continue
        if p in ("全球發售", "股份發售", "全球发售", "股份发售"):
            continue
        kws.append(p.lower())
    stem_l = stem.lower()
    kws.append(stem_l)
    extras = {
        "蜜雪": ["mixue", "蜜雪冰城", "蜜雪集团", "蜜雪集團"],
        "翰思": ["hanx", "翰思艾泰"],
        "快手": ["kuaishou"],
        "伊登": ["eden"],
        "建中": ["jianzhong"],
        "德合": ["dehe"],
    }
    for needle, aliases in extras.items():
        if needle in stem:
            kws.extend(aliases)
    if stem_l == "xiaomi" or "小米" in stem:
        kws.extend(["xiaomi", "小米", "01810"])
    if stem_l == "qiniu" or "七牛" in stem:
        kws.extend(["qiniu", "七牛", "02597"])

    seen: set[str] = set()
    out: list[str] = []
    for k in kws:
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return tuple(out)


def _find_pdf_for_key(key: str) -> Optional[Path]:
    if not PDF_DIR.is_dir():
        return None
    exact = PDF_DIR / f"{key}.pdf"
    if exact.is_file():
        return exact
    aliases = {
        "02097_21-02-2025_蜜雪集團_全球發售": ["mixue.pdf"],
        "xiaomi": ["xiaomi.pdf"],
        "qiniu": ["qiniu.pdf"],
    }
    for name in aliases.get(key, []):
        p = PDF_DIR / name
        if p.is_file():
            return p
    m = _TICKER_RE.match(key)
    if m:
        code = m.group(1)
        for p in sorted(PDF_DIR.glob("*.pdf")):
            if p.name.startswith(code):
                return p
    if key.lower() in ("xiaomi", "qiniu", "mixue"):
        p = PDF_DIR / f"{key.lower()}.pdf"
        if p.is_file():
            return p
    return None


def _resolve_parse_dir(child: Path) -> Optional[Path]:
    """返回含 preview.md + parse_summary.json 的目录。"""
    if (child / "preview.md").is_file() and (child / "parse_summary.json").is_file():
        return child
    for sub in sorted(child.iterdir()):
        if (
            sub.is_dir()
            and (sub / "preview.md").is_file()
            and (sub / "parse_summary.json").is_file()
        ):
            return sub
    return None


def discover_samples(samples_dir: Path = SAMPLES_DIR) -> List[SampleEntry]:
    entries: List[SampleEntry] = []
    if not samples_dir.is_dir():
        logger.warning("样本目录不存在: %s", samples_dir)
        return entries

    for child in sorted(samples_dir.iterdir()):
        if not child.is_dir() or child.name.endswith("-reparse"):
            continue
        parse_dir = _resolve_parse_dir(child)
        if parse_dir is None:
            continue

        key = child.name
        ticker = None
        m = _TICKER_RE.match(key)
        if m:
            ticker = m.group(1)
        elif key.lower() == "xiaomi":
            ticker = "01810"
        elif key.lower() == "qiniu":
            ticker = "02597"

        pdf_path = _find_pdf_for_key(key)
        sha = None
        if pdf_path is not None:
            try:
                sha = file_sha256(pdf_path)
            except OSError as e:
                logger.warning("无法计算 sha256 %s: %s", pdf_path, e)

        entries.append(
            SampleEntry(
                key=key,
                parse_dir=parse_dir,
                ticker=ticker,
                keywords=_keywords_from_stem(key),
                pdf_path=pdf_path,
                sha256=sha,
                page_count=_read_page_count(parse_dir),
            )
        )
    return entries


class SampleCatalog:
    def __init__(self, samples_dir: Path = SAMPLES_DIR) -> None:
        self.samples_dir = samples_dir
        self.entries: List[SampleEntry] = []
        self.by_sha: Dict[str, SampleEntry] = {}
        self.by_ticker: Dict[str, SampleEntry] = {}
        self.by_key: Dict[str, SampleEntry] = {}
        self.reload()

    def reload(self) -> None:
        self.entries = discover_samples(self.samples_dir)
        self.by_sha = {e.sha256: e for e in self.entries if e.sha256}
        self.by_ticker = {}
        for e in self.entries:
            if not e.ticker:
                continue
            self.by_ticker[e.ticker] = e
            self.by_ticker[f"{e.ticker}.HK"] = e
            self.by_ticker[f"{e.ticker}.hk"] = e
        self.by_key = {e.key: e for e in self.entries}
        logger.info(
            "样本目录已加载: %d 份 (sha=%d)",
            len(self.entries),
            len(self.by_sha),
        )

    def match(
        self,
        *,
        sha256: Optional[str] = None,
        ticker: Optional[str] = None,
        file_name: Optional[str] = None,
    ) -> Optional[SampleEntry]:
        if sha256 and sha256 in self.by_sha:
            return self.by_sha[sha256]

        if ticker:
            t = ticker.strip().upper().replace(" ", "")
            code = t.split(".")[0]
            if t in self.by_ticker:
                return self.by_ticker[t]
            if code in self.by_ticker:
                return self.by_ticker[code]
            code_nz = code.lstrip("0") or "0"
            for e in self.entries:
                if e.ticker and (e.ticker.lstrip("0") or "0") == code_nz:
                    return e

        if file_name:
            name = Path(file_name).stem.lower()
            for e in self.entries:
                if e.key.lower() == name or name in e.key.lower() or e.key.lower() in name:
                    return e
            for e in self.entries:
                for kw in e.keywords:
                    if kw and kw in name:
                        return e
        return None

    def default(self) -> Optional[SampleEntry]:
        for preferred in (
            "03378_15-12-2025_翰思艾泰－Ｂ_全球發售",
            "02097_21-02-2025_蜜雪集團_全球發售",
        ):
            if preferred in self.by_key:
                return self.by_key[preferred]
        return self.entries[0] if self.entries else None
