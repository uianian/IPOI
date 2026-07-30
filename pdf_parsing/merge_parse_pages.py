#!/usr/bin/env python3
"""
将定向重跑结果（patch）按页合并回全书 full_parse.json。

用法：
  python merge_parse_pages.py \\
    --base output/mixue/full_parse.json \\
    --patch output/mixue-reparse/full_parse.json \\
    --pages 16,21,430,431 \\
    -o output/mixue/full_parse.json

  # 不指定 --pages 则合并 patch 中出现的全部页
  python merge_parse_pages.py --base ... --patch ... -o ...

可选：
  --bbox-scale 2.4   将 patch 的 bbox 坐标按比例缩放（如 150DPI→300DPI）
  --prefer-higher-table-score  仅当 patch 的 table_quality_score 更高时才替换
  --annotate-pass reparse_rotate  写入页级 parse_pass 字段
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

try:
    from table_quality import annotate_table_confidence
except ImportError:
    annotate_table_confidence = None  # type: ignore


def parse_pages_csv(spec: Optional[str]) -> Optional[Set[int]]:
    if not spec:
        return None
    return {int(p.strip()) for p in spec.split(",") if p.strip()}


def load_pages(path: Path) -> Dict[int, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"期望页数组 JSON: {path}")
    return {int(p["page"]): p for p in data}


def scale_bbox(elem: dict, scale: float) -> dict:
    bbox = elem.get("bbox")
    if not (isinstance(bbox, list) and len(bbox) == 4):
        return elem
    out = dict(elem)
    out["bbox"] = [round(v * scale) for v in bbox]
    return out


def scale_page_bboxes(page: dict, scale: float) -> dict:
    if abs(scale - 1.0) < 1e-9:
        return page
    out = dict(page)
    out["elements"] = [scale_bbox(e, scale) for e in page.get("elements") or []]
    return out


def ensure_confidence(page: dict) -> dict:
    if page.get("table_structure_confidence") or annotate_table_confidence is None:
        return page
    elems = [dict(e) for e in (page.get("elements") or [])]
    if not any(e.get("category") == "table" for e in elems):
        return page
    meta = annotate_table_confidence(
        elems, rotation_applied=page.get("rotation_applied") or 0
    )
    out = dict(page)
    out["elements"] = elems
    out.update(meta)
    return out


def table_score(page: dict) -> int:
    if "table_quality_score" in page:
        return int(page["table_quality_score"] or 0)
    best = 0
    for e in page.get("elements") or []:
        if e.get("category") != "table":
            continue
        if "table_quality_score" in e:
            best = max(best, int(e["table_quality_score"] or 0))
            continue
        text = e.get("text") or ""
        rows = text.count("<tr>")
        import re

        nums = len(re.findall(r"[\d,]{4,}", text))
        best = max(best, rows * 100 + nums * 5 + len(text) // 20)
    return best


def merge(
    base: Dict[int, dict],
    patch: Dict[int, dict],
    pages: Optional[Set[int]],
    *,
    bbox_scale: float = 1.0,
    prefer_higher_table_score: bool = False,
    parse_pass: Optional[str] = None,
) -> tuple[List[dict], List[dict]]:
    """
    返回 (merged_sorted_pages, changelog)。
    changelog 每项: page, action, detail
    """
    target_pages = pages if pages is not None else set(patch.keys())
    changelog: List[Dict[str, Any]] = []

    for pnum in sorted(target_pages):
        if pnum not in patch:
            changelog.append(
                {"page": pnum, "action": "skip", "detail": "patch 中无此页"}
            )
            continue
        if pnum not in base:
            incoming = scale_page_bboxes(ensure_confidence(dict(patch[pnum])), bbox_scale)
            if parse_pass:
                incoming["parse_pass"] = parse_pass
            incoming["merged_at"] = datetime.now().isoformat(timespec="seconds")
            base[pnum] = incoming
            changelog.append(
                {"page": pnum, "action": "insert", "detail": "base 无此页，插入 patch"}
            )
            continue

        incoming = scale_page_bboxes(ensure_confidence(dict(patch[pnum])), bbox_scale)
        current = base[pnum]

        if prefer_higher_table_score:
            cur_s, new_s = table_score(current), table_score(incoming)
            # 无 table 时分数为 0：若 patch 有 table 而 base 无，仍应替换
            patch_has_table = any(
                e.get("category") == "table" for e in incoming.get("elements") or []
            )
            base_has_table = any(
                e.get("category") == "table" for e in current.get("elements") or []
            )
            if patch_has_table and not base_has_table:
                pass  # 强制替换
            elif new_s <= cur_s:
                changelog.append(
                    {
                        "page": pnum,
                        "action": "keep_base",
                        "detail": f"score patch={new_s} <= base={cur_s}",
                    }
                )
                continue

        if parse_pass:
            incoming["parse_pass"] = parse_pass
        incoming["merged_at"] = datetime.now().isoformat(timespec="seconds")
        incoming["merged_from_page"] = pnum
        base[pnum] = incoming
        changelog.append(
            {
                "page": pnum,
                "action": "replace",
                "detail": (
                    f"elems {len(current.get('elements') or [])} → "
                    f"{len(incoming.get('elements') or [])}; "
                    f"conf {current.get('table_structure_confidence')} → "
                    f"{incoming.get('table_structure_confidence')}"
                ),
            }
        )

    merged = [base[k] for k in sorted(base.keys())]
    return merged, changelog


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(
        description="将 patch full_parse 按页合并回 base",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--base", required=True, help="全书 full_parse.json")
    ap.add_argument("--patch", required=True, help="定向重跑 full_parse.json")
    ap.add_argument(
        "--pages",
        default=None,
        help="仅合并这些页（逗号分隔）；默认 patch 中全部页",
    )
    ap.add_argument("-o", "--output", required=True, help="合并后输出路径")
    ap.add_argument(
        "--bbox-scale",
        type=float,
        default=1.0,
        help="对 patch bbox 乘以此系数（150→300 DPI 约 2.0~2.5）",
    )
    ap.add_argument(
        "--prefer-higher-table-score",
        action="store_true",
        help="仅当 patch 表格质量分更高（或补回缺失 table）时替换",
    )
    ap.add_argument(
        "--annotate-pass",
        default="reparse",
        help="写入页级 parse_pass 标记；空字符串则不写",
    )
    ap.add_argument(
        "--backup",
        action="store_true",
        help="若 -o 覆盖已有文件，先备份为 *.bak",
    )
    args = ap.parse_args(argv)

    base_path = Path(args.base)
    patch_path = Path(args.patch)
    out_path = Path(args.output)

    base = load_pages(base_path)
    patch = load_pages(patch_path)
    pages = parse_pages_csv(args.pages)
    parse_pass = args.annotate_pass.strip() or None

    merged, changelog = merge(
        base,
        patch,
        pages,
        bbox_scale=args.bbox_scale,
        prefer_higher_table_score=args.prefer_higher_table_score,
        parse_pass=parse_pass,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if args.backup and out_path.exists():
        bak = out_path.with_suffix(out_path.suffix + ".bak")
        shutil.copy2(out_path, bak)
        print(f"已备份: {bak}")

    out_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    log_path = out_path.parent / "merge_changelog.json"
    log_path.write_text(
        json.dumps(
            {
                "base": str(base_path),
                "patch": str(patch_path),
                "pages": sorted(pages) if pages else "all_in_patch",
                "bbox_scale": args.bbox_scale,
                "prefer_higher_table_score": args.prefer_higher_table_score,
                "changelog": changelog,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    replaced = sum(1 for c in changelog if c["action"] in ("replace", "insert"))
    kept = sum(1 for c in changelog if c["action"] == "keep_base")
    skipped = sum(1 for c in changelog if c["action"] == "skip")
    print(f"合并完成: replace/insert={replaced}, keep_base={kept}, skip={skipped}")
    print(f"输出: {out_path}")
    print(f"变更日志: {log_path}")
    for c in changelog:
        if c["action"] != "skip":
            print(f"  p{c['page']}: {c['action']} — {c['detail']}")


if __name__ == "__main__":
    main()
