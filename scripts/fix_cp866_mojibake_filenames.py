#!/usr/bin/env python3
"""修复「UTF-8 中文被按 CP866 误解码」导致的文件名乱码。

典型症状：``全球發售`` 变成 ``хЕичРГчЩ╝хФо``（西里尔字母 + 制表符字形）。
恢复：``garbled.encode("cp866").decode("utf-8")``。

示例：
  python scripts/fix_cp866_mojibake_filenames.py --root dataset/18a --dry-run
  python scripts/fix_cp866_mojibake_filenames.py --root dataset/2025
  python scripts/fix_cp866_mojibake_filenames.py --root pdf_parsing/output/18a_batch
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

IPOI_ROOT = Path(__file__).resolve().parent.parent


def looks_like_cp866_mojibake(name: str) -> bool:
    """启发式：含西里尔字母，且常见「全球發售」乱码片段。"""
    has_cyrillic = any("\u0400" <= c <= "\u04FF" for c in name)
    if not has_cyrillic:
        return False
    markers = ("хЕичРГчЩ╝хФо", "шВбф╗╜чЩ╝хФо", "я╝Ня╝в", "я╝Ня╝╖")
    return any(m in name for m in markers) or ("╝" in name and "ч" in name)


def recover_cp866_mojibake(name: str) -> str | None:
    try:
        fixed = name.encode("cp866").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None
    if fixed == name:
        return None
    # 至少恢复出汉字，或后缀变成「發售」
    if any("\u4e00" <= c <= "\u9fff" for c in fixed) or "發售" in fixed:
        return fixed
    return None


def rename_path(src: Path, dry_run: bool) -> tuple[str, str] | None:
    fixed_name = recover_cp866_mojibake(src.name)
    if not fixed_name or not looks_like_cp866_mojibake(src.name):
        # still try recover if heuristic soft-fails but decode works
        if not fixed_name:
            return None
        if not looks_like_cp866_mojibake(src.name) and not any(
            "\u0400" <= c <= "\u04FF" for c in src.name
        ):
            return None
    dst = src.with_name(fixed_name)
    if dst == src:
        return None
    if dst.exists():
        print(f"SKIP exists: {src.name} -> {fixed_name}", file=sys.stderr)
        return None
    print(f"{'[dry-run] ' if dry_run else ''}{src.name}\n  -> {fixed_name}")
    if not dry_run:
        src.rename(dst)
    return src.name, fixed_name


def patch_batch_summary(batch_dir: Path, mapping: dict[str, str], dry_run: bool) -> None:
    summary = batch_dir / "batch_summary.json"
    if not summary.is_file():
        return
    data = json.loads(summary.read_text(encoding="utf-8"))
    changed = 0
    for rec in data.get("records") or []:
        stem = rec.get("stem")
        if stem in mapping:
            new_stem = mapping[stem]
            rec["stem"] = new_stem
            if "out_dir" in rec:
                rec["out_dir"] = str(Path(rec["out_dir"]).with_name(new_stem))
            if "pdf" in rec and isinstance(rec["pdf"], str):
                # only rewrite basename if it matches old stem
                pdf_path = Path(rec["pdf"])
                if pdf_path.stem == stem or pdf_path.name.startswith(stem):
                    rec["pdf"] = str(pdf_path.with_name(new_stem + pdf_path.suffix))
            changed += 1
    if changed:
        print(f"batch_summary.json: patch {changed} records")
        if not dry_run:
            summary.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix CP866-mojibake filenames")
    parser.add_argument(
        "--root",
        type=Path,
        required=True,
        help="目录（文件或子目录名会被检查）",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--codes",
        default="",
        help="仅处理这些股票代码前缀，逗号分隔（如 02561,02565）",
    )
    args = parser.parse_args()
    root = args.root
    if not root.is_absolute():
        root = (IPOI_ROOT / root).resolve()
    if not root.is_dir():
        print(f"ERROR: not a directory: {root}", file=sys.stderr)
        return 1

    code_set = {c.strip() for c in args.codes.split(",") if c.strip()}
    mapping: dict[str, str] = {}
    n = 0
    for p in sorted(root.iterdir()):
        if code_set and not any(p.name.startswith(c + "_") or p.name.startswith(c) for c in code_set):
            # allow exact code prefix
            if not any(p.name.startswith(c) for c in code_set):
                continue
        if not looks_like_cp866_mojibake(p.name) and not any(
            "\u0400" <= c <= "\u04FF" for c in p.name
        ):
            continue
        result = rename_path(p, dry_run=args.dry_run)
        if result:
            old, new = result
            mapping[Path(old).stem if old.endswith(".pdf") else old] = (
                Path(new).stem if new.endswith(".pdf") else new
            )
            # also map with .pdf
            mapping[old] = new
            n += 1

    if (root / "batch_summary.json").is_file():
        # map stems only
        stem_map = {
            (k[:-4] if k.endswith(".pdf") else k): (v[:-4] if v.endswith(".pdf") else v)
            for k, v in mapping.items()
        }
        patch_batch_summary(root, stem_map, dry_run=args.dry_run)

    print(f"\nDone: {n} renames under {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
