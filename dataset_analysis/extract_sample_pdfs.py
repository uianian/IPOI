#!/usr/bin/env python3
"""将 sample_list.csv 中的抽样招股书 PDF 复制到目标目录。

设计用于「本地解压后抽取」场景：
- 不依赖 catalog 里记录的服务器绝对路径（如 /nfs/users/...）
- 在 --source-dataset-root 下按 stock_code 前缀递归查找 PDF
- 复制时保持磁盘上的原始文件名不变（含乱码文件名）

用法示例（本地）：
  python dataset_analysis/extract_sample_pdfs.py \\
    --source-dataset-root ./dataset \\
    --sample-list ./dataset_analysis/output/sample_list.csv \\
    --dest ./dataset/sample

也可使用配置文件：
  python dataset_analysis/extract_sample_pdfs.py --config dataset_analysis/local_extract_config.json
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SAMPLE_LIST = PROJECT_ROOT / "dataset_analysis/output/sample_list.csv"
DEFAULT_CATALOG = PROJECT_ROOT / "dataset_analysis/output/ipo_catalog_with_metrics.csv"
DEFAULT_SOURCE_DATASET = PROJECT_ROOT / "dataset"
DEFAULT_DEST = PROJECT_ROOT / "dataset/sample"
DEFAULT_CONFIG = PROJECT_ROOT / "dataset_analysis/local_extract_config.json"
EXAMPLE_CONFIG = PROJECT_ROOT / "dataset_analysis/local_extract_config.example.json"

STOCK_CODE_PATTERN = re.compile(r"^(\d{5})_")


def resolve_path(path: Path | str, base: Path = PROJECT_ROOT) -> Path:
    p = Path(path)
    return p if p.is_absolute() else (base / p).resolve()


def load_config(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def load_sample_list(sample_list: Path) -> pd.DataFrame:
    df = pd.read_csv(sample_list, encoding="utf-8-sig", dtype={"stock_code": str})
    df["stock_code"] = df["stock_code"].astype(str).str.zfill(5)
    return df.drop_duplicates("stock_code").reset_index(drop=True)


def parse_stock_code_from_filename(filename: str) -> Optional[str]:
    match = STOCK_CODE_PATTERN.match(filename)
    return match.group(1) if match else None


def build_pdf_index(dataset_root: Path) -> Dict[str, List[Path]]:
    """递归扫描 dataset_root，按 5 位股票代码建立 PDF 索引。"""
    index: Dict[str, List[Path]] = {}
    if not dataset_root.is_dir():
        return index

    for pdf in dataset_root.rglob("*.pdf"):
        if pdf.parent.name == "sample":
            continue
        code = parse_stock_code_from_filename(pdf.name)
        if not code:
            continue
        index.setdefault(code, []).append(pdf)
    return index


def choose_pdf(candidates: List[Path], preferred_filename: Optional[str] = None) -> Optional[Path]:
    if not candidates:
        return None
    if preferred_filename:
        for path in candidates:
            if path.name == preferred_filename:
                return path
    if len(candidates) == 1:
        return candidates[0]
    return sorted(candidates, key=lambda p: str(p))[0]


def locate_pdf(
    stock_code: str,
    pdf_index: Dict[str, List[Path]],
    dataset_root: Path,
    preferred_filename: Optional[str] = None,
    legacy_path: Optional[str] = None,
) -> Optional[Path]:
    code = str(stock_code).zfill(5)

    hit = choose_pdf(pdf_index.get(code, []), preferred_filename)
    if hit:
        return hit

    if legacy_path:
        legacy = Path(legacy_path)
        if legacy.is_file():
            return legacy
        legacy_name = legacy.name
        for pdf in dataset_root.rglob(legacy_name):
            if pdf.is_file():
                return pdf

    if preferred_filename:
        for pdf in dataset_root.rglob(preferred_filename):
            if pdf.is_file():
                return pdf

    return None


def enrich_with_catalog(sample_df: pd.DataFrame, catalog: Optional[Path]) -> pd.DataFrame:
    if catalog is None or not Path(catalog).is_file():
        return sample_df

    catalog_df = pd.read_csv(catalog, encoding="utf-8-sig", dtype={"stock_code": str})
    catalog_df["stock_code"] = catalog_df["stock_code"].astype(str).str.zfill(5)
    extra_cols = [c for c in ["pdf_filename", "pdf_path", "folder_year"] if c in catalog_df.columns]
    if not extra_cols:
        return sample_df
    return sample_df.merge(catalog_df[["stock_code"] + extra_cols], on="stock_code", how="left")


def extract_sample_pdfs(
    sample_list: Path,
    source_dataset_root: Path,
    dest_dir: Path,
    catalog: Optional[Path] = None,
    overwrite: bool = True,
) -> dict:
    sample_list = resolve_path(sample_list)
    source_dataset_root = resolve_path(source_dataset_root)
    dest_dir = resolve_path(dest_dir)
    catalog = resolve_path(catalog) if catalog else None

    sample_df = load_sample_list(sample_list)
    sample_df = enrich_with_catalog(sample_df, catalog)
    pdf_index = build_pdf_index(source_dataset_root)

    if overwrite and dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    copied, missing = [], []
    manifest_rows = []

    for _, row in sample_df.iterrows():
        code = row["stock_code"]
        preferred = row.get("pdf_filename") if pd.notna(row.get("pdf_filename")) else None
        legacy = row.get("pdf_path") if pd.notna(row.get("pdf_path")) else None

        src = locate_pdf(code, pdf_index, source_dataset_root, preferred, legacy)
        if src is None:
            missing.append({
                "stock_code": code,
                "company_name": row.get("company_name"),
                "preferred_filename": preferred,
            })
            continue

        dst = dest_dir / src.name
        shutil.copy2(src, dst)
        copied.append(src.name)

        manifest_rows.append({
            "stock_code": code,
            "company_name": row.get("company_name"),
            "company_display": row.get("company_display", row.get("company_name")),
            "list_year": row.get("list_year"),
            "performance_class": row.get("performance_class"),
            "sample_reason": row.get("sample_reason"),
            "source_pdf_filename": src.name,
            "source_pdf_path": str(src),
            "dest_pdf_path": str(dst),
        })

    manifest = pd.DataFrame(manifest_rows)
    manifest_path = dest_dir / "sample_manifest.csv"
    manifest.to_csv(manifest_path, index=False, encoding="utf-8-sig")

    return {
        "dest_dir": str(dest_dir),
        "source_dataset_root": str(source_dataset_root),
        "total": len(sample_df),
        "copied": len(copied),
        "missing": missing,
        "manifest": str(manifest_path),
    }


def write_example_config(path: Path = EXAMPLE_CONFIG) -> None:
    example = {
        "sample_list": "dataset_analysis/output/sample_list.csv",
        "source_dataset_root": "dataset",
        "dest_dir": "dataset/sample",
        "catalog": "dataset_analysis/output/ipo_catalog_with_metrics.csv",
        "overwrite": True,
        "_notes": {
            "source_dataset_root": "本地解压后的招股书根目录，可含 2020-2025 子文件夹，脚本会递归按 stock_code 查找",
            "pdf_filename": "磁盘文件名保持不变；2025 年乱码文件名不影响匹配，靠 stock_code 前缀定位",
            "paths": "相对路径均相对于项目根目录；也可写绝对路径",
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(example, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="按 sample_list 的 stock_code 从本地 dataset 目录取出 PDF（不依赖服务器绝对路径）"
    )
    parser.add_argument("--config", type=Path, default=None, help="JSON 配置文件路径")
    parser.add_argument("--sample-list", type=Path, default=None)
    parser.add_argument("--source-dataset-root", type=Path, default=None, help="本地 PDF 根目录")
    parser.add_argument("--catalog", type=Path, default=None, help="可选，仅用于补充 pdf_filename 等元数据")
    parser.add_argument("--dest", type=Path, default=None, help="输出目录")
    parser.add_argument("--no-overwrite", action="store_true", help="不清空目标目录")
    parser.add_argument("--write-example-config", action="store_true", help="生成 local_extract_config.example.json")
    args = parser.parse_args()

    if args.write_example_config:
        write_example_config()
        print(f"已生成示例配置: {EXAMPLE_CONFIG}")
        return

    cfg = {}
    if args.config:
        cfg = load_config(resolve_path(args.config))

    sample_list = args.sample_list or cfg.get("sample_list") or DEFAULT_SAMPLE_LIST
    source_root = args.source_dataset_root or cfg.get("source_dataset_root") or DEFAULT_SOURCE_DATASET
    catalog = args.catalog if args.catalog is not None else cfg.get("catalog", DEFAULT_CATALOG)
    dest = args.dest or cfg.get("dest_dir") or cfg.get("dest") or DEFAULT_DEST
    overwrite = not args.no_overwrite and cfg.get("overwrite", True)

    result = extract_sample_pdfs(
        sample_list=sample_list,
        source_dataset_root=source_root,
        dest_dir=dest,
        catalog=catalog,
        overwrite=overwrite,
    )

    print(f"PDF 源目录: {result['source_dataset_root']}")
    print(f"目标目录: {result['dest_dir']}")
    print(f"复制完成: {result['copied']} / {result['total']} 份")
    print(f"清单文件: {result['manifest']}")
    if result["missing"]:
        print("以下样本未找到对应 PDF（请检查 source_dataset_root 或解压是否完整）:")
        for item in result["missing"]:
            print(f"  {item['stock_code']} {item.get('company_name', '')} preferred={item.get('preferred_filename')}")


if __name__ == "__main__":
    main()
