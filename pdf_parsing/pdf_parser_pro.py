#!/usr/bin/env python3
"""
IPO 招股书 PDF 解析器（生产版）。

在 pdf_parser.py（官方 Infinity-Parser2 对齐）基础上，吸收 parse_prospectus.py 的下游能力：
  - JSON 为主输出（表格保留 HTML，不做 HTML→Markdown 强转）
  - Markdown 仅作可读预览（preview.md）
  - 风险 chunk 抽取（risk_chunks.json，供 RAG 入库）
  - 页级 parse_status 与官方 postprocess_doc2json_result 截断修复

保留：PyMuPDF 300 DPI、页级 batch 推理、官方后处理、figure 裁剪。
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import torch
from PIL import Image
from qwen_vl_utils import process_vision_info
from transformers import AutoModelForImageTextToText, AutoProcessor

# ── 官方后处理（绕过包 __init__）────────────────────────────
_INF_UTILS_PATH = (
    Path(__file__).resolve().parent
    / "INF-MLLM" / "Infinity-Parser2" / "infinity_parser2" / "utils" / "utils.py"
)
if not _INF_UTILS_PATH.is_file():
    raise ImportError(f"找不到官方后处理模块: {_INF_UTILS_PATH}")

_spec = importlib.util.spec_from_file_location("_inf_postprocess", _INF_UTILS_PATH)
_inf_postprocess = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_inf_postprocess)
postprocess_doc2json_result = _inf_postprocess.postprocess_doc2json_result
truncate_last_incomplete_element = _inf_postprocess.truncate_last_incomplete_element
extract_json_content = _inf_postprocess.extract_json_content

# ── 默认参数 ───────────────────────────────────────────────
DEFAULT_MODEL = "./models/infly/Infinity-Parser2-Flash"
DEFAULT_DPI = 300
DEFAULT_BATCH_SIZE = 4
# 32768 会让 batch 内被超长页拖死；16384 对招股书页足够，截断仍有 truncate 修复
DEFAULT_MAX_NEW_TOKENS = 16384
MIN_PIXELS = 2048
MAX_PIXELS = 16777216
# 旋转版表格分已够高时跳过原向二次推理（省掉几乎一整页耗时）
ROTATE_FALLBACK_SKIP_SCORE = 800

PARSE_PROMPT = """
- Extract layout information from the provided PDF image.
- For each layout element, output its bbox, category, and the text content within the bbox.
- Bbox format: [x1, y1, x2, y2].
- Allowed layout categories: ['header', 'title', 'text', 'figure', 'table', 'formula', 'figure_caption', 'table_caption', 'figure_footnote', 'table_footnote', 'page_footnote', 'footer'].
- Text extraction and formatting:
  1) For 'figure', the text field must be an empty string.
  2) For 'formula', format text as LaTeX.
  3) For 'table', format text as HTML (use <table> with colspan/rowspan where needed).
  4) For all other categories (e.g., text, title), format text as Markdown.
- The output text must be exactly the original text from the image, with no translation or rewriting.
- Sort all layout elements in human reading order.
- Final output must be a single JSON object.
""".strip()

RISK_KEYWORDS = [
    "風險因素", "對賭", "贖回", "關聯交易", "現金消耗",
    "重大不確定", "核心管線", "虧損", "訴訟", "質押",
    "风险因素", "对赌", "赎回", "关联交易", "现金消耗",
]

PREVIEW_SKIP_CATEGORIES = frozenset({"header", "footer", "page_footnote"})

# rotate_mode: none | auto | cw90 | ccw90 | 180 | manual
ROTATE_MODES = ("none", "auto", "cw90", "ccw90", "180", "manual")
ROTATE_MODE_TO_DEGREES = {
    "none": 0,
    "cw90": 90,
    "ccw90": 270,
    "180": 180,
}


# ── 页面旋转（竖表 / 页内局部旋转）──────────────────────────
def rotate_image_cw(image: Image.Image, degrees_cw: int) -> Image.Image:
    """顺时针旋转页面图像。PIL rotate 正角为逆时针，故取负值。"""
    if degrees_cw % 360 == 0:
        return image
    return image.rotate(-(degrees_cw % 360), expand=True, resample=Image.Resampling.BICUBIC)


def detect_vertical_table_rotation(pdf_path: Union[str, Path], page_index: int) -> int:
    """
    基于 PyMuPDF 文本块几何特征检测竖表页，返回建议顺时针旋转角度（0 或 90）。
    蜜雪 1-30 样本：仅第 16、21 页触发（vertical_blocks >= 5）。
    """
    import fitz

    doc = fitz.open(str(pdf_path))
    page = doc[page_index]
    page_w, page_h = page.rect.width, page.rect.height
    vertical_blocks = 0

    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        x0, y0, x1, y1 = block["bbox"]
        w = max(x1 - x0, 1.0)
        h = max(y1 - y0, 1.0)
        if h / w > 3.5 and w < page_w * 0.12 and h > page_h * 0.15:
            vertical_blocks += 1

    doc.close()
    return 90 if vertical_blocks >= 5 else 0


def resolve_page_rotation(
    pdf_path: Union[str, Path],
    page_num: int,
    rotate_mode: str,
    rotate_pages: Optional[set[int]] = None,
    manual_degrees: int = 0,
) -> int:
    """返回该页顺时针旋转角度（0/90/180/270）。"""
    if rotate_mode == "none":
        return 0
    if rotate_pages is not None and page_num not in rotate_pages:
        return 0

    if rotate_mode == "auto":
        return detect_vertical_table_rotation(pdf_path, page_num - 1)
    if rotate_mode == "manual":
        return manual_degrees % 360
    return ROTATE_MODE_TO_DEGREES.get(rotate_mode, 0)


def parse_rotate_pages(spec: Optional[str]) -> Optional[set[int]]:
    if not spec:
        return None
    return {int(p.strip()) for p in spec.split(",") if p.strip()}


from table_quality import (  # noqa: E402
    annotate_table_confidence,
    assess_single_table,
    score_table_html,
    score_table_quality,
)

def parse_single_page_raw(
    page_image: Image.Image,
    model,
    processor,
    max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
) -> str:
    """单页推理，供旋转回退对比使用。"""
    return parse_pages_batch(
        [page_image], model, processor, batch_size=1, max_new_tokens=max_new_tokens
    )[0]

def convert_pdf_to_images(pdf_path: Union[str, Path], dpi: int = 300) -> List[Image.Image]:
    try:
        import fitz
    except ImportError as e:
        raise ImportError("PyMuPDF 未安装，请执行: pip install pymupdf") from e

    Image.MAX_IMAGE_PIXELS = None
    doc = fitz.open(str(pdf_path))
    images: List[Image.Image] = []
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    for page_num in range(len(doc)):
        pix = doc[page_num].get_pixmap(matrix=mat, alpha=False)
        images.append(Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB"))
    doc.close()
    return images


def render_pdf_pages(
    pdf_path: Union[str, Path],
    dpi: int = DEFAULT_DPI,
    *,
    page_numbers: Optional[List[int]] = None,
) -> List[Image.Image]:
    """渲染 PDF；page_numbers 为 1-based 页码列表，None 表示全部页。"""
    all_images = convert_pdf_to_images(str(pdf_path), dpi=dpi)
    if page_numbers is None:
        return all_images
    return [all_images[p - 1] for p in page_numbers if 0 < p <= len(all_images)]


# ── 模型 ───────────────────────────────────────────────────
def load_model(model_name: str = DEFAULT_MODEL, device_map: str = "auto"):
    model = AutoModelForImageTextToText.from_pretrained(
        model_name,
        torch_dtype=torch.bfloat16,
        device_map=device_map,
        trust_remote_code=True,
    )
    processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=True)
    return model, processor


def parse_pages_batch(
    page_images: List[Image.Image],
    model,
    processor,
    prompt: str = PARSE_PROMPT,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
    progress_callback=None,
) -> List[str]:
    results: List[str] = []

    for start in range(0, len(page_images), batch_size):
        batch = page_images[start : start + batch_size]
        end = min(start + batch_size, len(page_images))
        print(f"  推理第 {start + 1}-{end}/{len(page_images)} 页...", flush=True)

        messages = [
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "image": img,
                            "min_pixels": MIN_PIXELS,
                            "max_pixels": MAX_PIXELS,
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ]
            for img in batch
        ]

        text = processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        image_inputs, _ = process_vision_info(messages, image_patch_size=16)

        inputs = processor(
            text=text,
            images=image_inputs,
            do_resize=False,
            padding=True,
            return_tensors="pt",
        )
        inputs.pop("token_type_ids", None)
        inputs = {
            k: v.to(model.device) if isinstance(v, torch.Tensor) else v
            for k, v in inputs.items()
        }

        with torch.inference_mode():
            generated_ids = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=0.0,
                top_p=1.0,
                do_sample=False,
                use_cache=True,
            )

        generated_ids_trimmed = [
            out_ids[len(in_ids) :]
            for in_ids, out_ids in zip(inputs["input_ids"], generated_ids)
        ]
        batch_text = processor.batch_decode(
            generated_ids_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )
        results.extend(batch_text)
        if progress_callback is not None:
            progress_callback(end)

    return results


# ── 后处理（官方 pipeline + 失败标记）──────────────────────
def _looks_like_layout_json(text: str) -> bool:
    return '"bbox"' in text and '"category"' in text


def postprocess_page(
    raw_text: str,
    page_image: Image.Image,
) -> Tuple[List[dict], Dict[str, Any]]:
    """
    单页后处理：官方 extract → truncate → bbox 还原 → JSON 解析。
    解析失败时保留 postprocess 后的 JSON 字符串供排查，不降级为整页纯文本块。
    """
    meta: Dict[str, Any] = {
        "parse_status": "ok",
        "element_count": 0,
        "truncated": False,
    }

    json_str = postprocess_doc2json_result(raw_text, page_image, output_format="json")

    extracted = extract_json_content(raw_text)
    _, was_truncated = truncate_last_incomplete_element(extracted)
    meta["truncated"] = was_truncated

    try:
        elements = json.loads(json_str)
        if isinstance(elements, list) and elements:
            meta["element_count"] = len(elements)
            return elements, meta
    except json.JSONDecodeError as exc:
        meta["parse_status"] = "failed"
        meta["error"] = str(exc)
        meta["postprocessed_json"] = json_str[:2000]

    # 二次尝试：postprocess 已截断修复，若仍失败则标记为 failed 并留空 elements
    if _looks_like_layout_json(json_str):
        meta["parse_status"] = "partial"
        meta["note"] = "postprocess 完成但 JSON 仍不可解析，请检查 postprocessed_json"

    return [], meta


def element_to_preview_md(elem: dict) -> str:
    """预览 Markdown：表格保留 HTML，figure 占位，不做 HTML→MD 表格转换。"""
    category = elem.get("category", "text")
    text = (elem.get("text") or "").strip()

    if category == "figure":
        image_path = elem.get("image_path", "")
        if image_path:
            return f"![figure]({image_path})"
        return "> 🖼️ *[图片区域 — 未提取 OCR 文本]*"

    if category == "table":
        if text.startswith("<"):
            return f"<!-- table html -->\n{text}\n<!-- /table -->"
        # 模型偶发输出 Markdown 表格，原样保留
        return f"<!-- table -->\n{text}\n<!-- /table -->"

    return text


def page_to_preview_markdown(
    page_num: int,
    elements: List[dict],
    *,
    include_header_footer: bool = False,
) -> str:
    lines = [f"## 第 {page_num} 页", ""]
    for elem in elements:
        cat = elem.get("category", "")
        if not include_header_footer and cat in PREVIEW_SKIP_CATEGORIES:
            continue
        block = element_to_preview_md(elem)
        if block:
            lines.append(block)
            lines.append("")
    return "\n".join(lines).rstrip()


def extract_risk_chunks(doc_result: List[dict]) -> List[dict]:
    """输出 RAG 友好的 chunk 列表，每个 chunk 带页码 + bbox 用于溯源。"""
    chunks: List[dict] = []
    for page_data in doc_result:
        page_num = page_data["page"]
        for elem in page_data.get("elements", []):
            category = elem.get("category", "")
            text = elem.get("text", "") or ""
            bbox = elem.get("bbox", [])

            if category == "table" and text.strip():
                chunks.append({
                    "page": page_num,
                    "bbox": bbox,
                    "type": "table",
                    "content": text,
                    "source_tag": f"p{page_num}_table",
                })
            elif category in ("text", "title") and any(kw in text for kw in RISK_KEYWORDS):
                chunks.append({
                    "page": page_num,
                    "bbox": bbox,
                    "type": "text",
                    "content": text,
                    "source_tag": f"p{page_num}_text",
                })
    return chunks


def save_figure_crops(
    page_image: Image.Image,
    elements: List[dict],
    page_num: int,
    figures_dir: Path,
    out_dir: Path,
) -> None:
    figures_dir.mkdir(parents=True, exist_ok=True)
    w, h = page_image.size
    fig_idx = 0

    for elem in elements:
        if elem.get("category") != "figure":
            continue
        bbox = elem.get("bbox", [])
        if not (isinstance(bbox, list) and len(bbox) == 4):
            continue

        x1, y1, x2, y2 = (int(v) for v in bbox)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            continue

        fig_idx += 1
        crop_path = figures_dir / f"p{page_num:04d}_fig{fig_idx:03d}.png"
        page_image.crop((x1, y1, x2, y2)).save(crop_path)
        # 分片并行时 figures_dir 在文档根、out_dir 是 _shard*/；
        # relative_to(out_dir) 会失败，应相对文档输出根（figures 的父目录）。
        crop_path = crop_path.resolve()
        bases = (Path(out_dir).resolve(), Path(figures_dir).resolve().parent)
        rel = None
        for base in bases:
            try:
                rel = crop_path.relative_to(base)
                break
            except ValueError:
                continue
        elem["image_path"] = str(rel) if rel is not None else str(crop_path)


def build_parse_summary(doc_result: List[dict]) -> dict:
    cats: Dict[str, int] = {}
    failed_pages: List[int] = []
    empty_pages: List[int] = []
    html_tables = 0
    md_tables = 0

    for page in doc_result:
        pnum = page["page"]
        if page.get("parse_status") != "ok":
            failed_pages.append(pnum)
        elems = page.get("elements", [])
        if not elems:
            empty_pages.append(pnum)
        for e in elems:
            c = e.get("category", "unknown")
            cats[c] = cats.get(c, 0) + 1
            if c == "table":
                t = (e.get("text") or "").strip()
                if t.startswith("<"):
                    html_tables += 1
                elif t:
                    md_tables += 1

    table_conf_pages = {
        k: sum(1 for p in doc_result if p.get("table_structure_confidence") == k)
        for k in ("high", "medium", "low")
    }

    return {
        "total_pages": len(doc_result),
        "total_elements": sum(len(p.get("elements", [])) for p in doc_result),
        "categories": dict(sorted(cats.items(), key=lambda x: -x[1])),
        "failed_pages": failed_pages,
        "empty_pages": empty_pages,
        "html_tables": html_tables,
        "markdown_tables": md_tables,
        "table_structure_confidence_pages": table_conf_pages,
    }


def parse_pdf(
    pdf_path: Union[str, Path],
    model,
    processor,
    dpi: int = DEFAULT_DPI,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
    save_figures: bool = True,
    figures_dir: Optional[Path] = None,
    out_dir: Optional[Path] = None,
    page_numbers: Optional[List[int]] = None,
    rotate_mode: str = "none",
    rotate_pages: Optional[set[int]] = None,
    rotate_degrees: int = 0,
    rotate_fallback: bool = False,
    progress_callback=None,
) -> Tuple[List[dict], str]:
    pdf_path = Path(pdf_path)
    print(f"正在渲染 PDF: {pdf_path} (PyMuPDF, {dpi} DPI)")
    page_images = render_pdf_pages(pdf_path, dpi=dpi, page_numbers=page_numbers)
    if page_numbers is None:
        page_nums = list(range(1, len(page_images) + 1))
    else:
        page_nums = page_numbers

    original_images = list(page_images)
    rotated_images: List[Image.Image] = []
    rotation_map: Dict[int, int] = {}
    for page_num, img in zip(page_nums, page_images):
        deg = resolve_page_rotation(
            pdf_path, page_num, rotate_mode, rotate_pages, rotate_degrees
        )
        rotation_map[page_num] = deg
        if deg:
            print(f"  第 {page_num} 页旋转 {deg}°（顺时针）", flush=True)
        rotated_images.append(rotate_image_cw(img, deg))

    fallback_note = "，旋转质量回退=开" if rotate_mode == "auto" and rotate_fallback else ""
    print(
        f"共 {len(rotated_images)} 页，batch_size={batch_size}，"
        f"rotate_mode={rotate_mode}{fallback_note}，开始推理...",
        flush=True,
    )

    raw_outputs = parse_pages_batch(
        rotated_images,
        model,
        processor,
        batch_size=batch_size,
        max_new_tokens=max_new_tokens,
        progress_callback=progress_callback,
    )

    if out_dir is None:
        out_dir = Path("output") / pdf_path.stem
    if figures_dir is None:
        figures_dir = out_dir / "figures"

    doc_result: List[dict] = []
    preview_pages: List[str] = []

    for i, (page_img, raw_text) in enumerate(zip(rotated_images, raw_outputs)):
        page_num = page_nums[i]
        orig_img = original_images[i]
        applied_deg = rotation_map.get(page_num, 0)
        elements, meta = postprocess_page(raw_text, page_img)

        # auto 模式：旋转后若表格质量不如原向，回退为 none
        if (
            rotate_mode == "auto"
            and rotate_fallback
            and applied_deg
        ):
            rot_score = score_table_quality(elements)
            # 旋转版已明显有完整表体时，跳过原向二次推理（省 ~1 页时间）
            if rot_score >= ROTATE_FALLBACK_SKIP_SCORE and any(
                e.get("category") == "table" for e in elements
            ):
                print(
                    f"  第 {page_num} 页跳过回退推理：rot_score={rot_score} "
                    f">= {ROTATE_FALLBACK_SKIP_SCORE}",
                    flush=True,
                )
            else:
                none_elements, none_meta = postprocess_page(
                    parse_single_page_raw(
                        orig_img, model, processor, max_new_tokens
                    ),
                    orig_img,
                )
                none_score = score_table_quality(none_elements)
                if none_score > rot_score:
                    print(
                        f"  第 {page_num} 页旋转回退：rot={rot_score} < none={none_score}，保留原向",
                        flush=True,
                    )
                    elements, meta = none_elements, none_meta
                    applied_deg = 0
                else:
                    print(
                        f"  第 {page_num} 页保留旋转：rot={rot_score} >= none={none_score}",
                        flush=True,
                    )

        if save_figures and elements:
            crop_img = rotate_image_cw(orig_img, applied_deg) if applied_deg else orig_img
            save_figure_crops(crop_img, elements, page_num, figures_dir, out_dir)

        page_record = {
            "page": page_num,
            "parse_status": meta["parse_status"],
            "elements": elements,
        }
        if applied_deg:
            page_record["rotation_applied"] = applied_deg
        elif applied_deg != rotation_map.get(page_num, 0) and rotation_map.get(page_num):
            page_record["rotation_skipped"] = True
            page_record["rotation_attempted"] = rotation_map[page_num]
        if meta.get("truncated"):
            page_record["truncated"] = True
        if meta.get("error"):
            page_record["parse_error"] = meta["error"]
        if meta.get("postprocessed_json") and meta["parse_status"] != "ok":
            page_record["postprocessed_json_preview"] = meta["postprocessed_json"]

        # 表格结构置信度（元素级 + 页级）
        conf_meta = annotate_table_confidence(
            elements, rotation_applied=applied_deg
        )
        page_record.update(conf_meta)

        doc_result.append(page_record)
        preview_pages.append(page_to_preview_markdown(page_num, elements))

    preview_md = "\n\n---\n\n".join(preview_pages)
    print(f"完成：{pdf_path}")
    return doc_result, preview_md


def save_outputs(
    out_dir: Path,
    doc_result: List[dict],
    preview_md: str,
    *,
    save_risk_chunks: bool = True,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    full_json_path = out_dir / "full_parse.json"
    with open(full_json_path, "w", encoding="utf-8") as f:
        json.dump(doc_result, f, ensure_ascii=False, indent=2)

    preview_path = out_dir / "preview.md"
    with open(preview_path, "w", encoding="utf-8") as f:
        f.write(preview_md)

    summary = build_parse_summary(doc_result)
    summary_path = out_dir / "parse_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    if save_risk_chunks:
        chunks = extract_risk_chunks(doc_result)
        chunks_path = out_dir / "risk_chunks.json"
        with open(chunks_path, "w", encoding="utf-8") as f:
            json.dump(chunks, f, ensure_ascii=False, indent=2)
        print(f"风险 chunks: {chunks_path}（共 {len(chunks)} 条）")

    print(f"完整 JSON:  {full_json_path}")
    print(f"预览 MD:    {preview_path}")
    print(f"解析摘要:   {summary_path}")
    if summary["failed_pages"]:
        print(f"⚠ 解析失败页: {summary['failed_pages']}")


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Infinity-Parser2-Flash PDF 解析（IPO 生产版）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("input", help="PDF 文件路径，或包含 *.pdf 的目录")
    p.add_argument("-o", "--output-dir", default=None, help="输出根目录")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    p.add_argument("--max-new-tokens", type=int, default=DEFAULT_MAX_NEW_TOKENS)
    p.add_argument("--no-figures", action="store_true")
    p.add_argument("--no-risk-chunks", action="store_true")
    p.add_argument("--device-map", default="auto")
    p.add_argument(
        "--pages",
        default=None,
        help="仅解析指定页（1-based，逗号分隔），如 16,21",
    )
    p.add_argument(
        "--rotate-mode",
        choices=ROTATE_MODES,
        default="none",
        help="none=仅PDF页级/Rotate; auto=竖表检测后CW90; cw90/ccw90/180; manual=配合--rotate-degrees",
    )
    p.add_argument(
        "--rotate-pages",
        default=None,
        help="仅对指定页应用旋转（1-based，逗号分隔）；省略则对所有页按 rotate-mode 处理",
    )
    p.add_argument(
        "--rotate-degrees",
        type=int,
        default=90,
        help="rotate-mode=manual 时的顺时针角度",
    )
    p.add_argument(
        "--rotate-fallback",
        action="store_true",
        help="auto 模式下启用旋转质量回退（旋转版与原向版择优，默认关闭）",
    )
    return p


def collect_pdf_paths(input_path: str) -> List[Path]:
    path = Path(input_path)
    if path.is_file():
        if path.suffix.lower() != ".pdf":
            raise ValueError(f"不支持的文件类型: {path}")
        return [path]
    if path.is_dir():
        pdfs = sorted(path.glob("*.pdf"))
        if not pdfs:
            raise ValueError(f"目录中未找到 PDF: {path}")
        return pdfs
    raise FileNotFoundError(f"路径不存在: {path}")


def main(argv: Optional[List[str]] = None) -> None:
    args = build_argparser().parse_args(argv)
    pdf_paths = collect_pdf_paths(args.input)

    print(f"加载模型: {args.model} (device_map={args.device_map})")
    model, processor = load_model(args.model, device_map=args.device_map)

    for pdf_path in pdf_paths:
        out_dir = (
            Path(args.output_dir) / pdf_path.stem
            if args.output_dir
            else Path("output") / pdf_path.stem
        )
        page_numbers = None
        if args.pages:
            page_numbers = [int(p.strip()) for p in args.pages.split(",") if p.strip()]

        doc_result, preview_md = parse_pdf(
            pdf_path,
            model,
            processor,
            dpi=args.dpi,
            batch_size=args.batch_size,
            max_new_tokens=args.max_new_tokens,
            save_figures=not args.no_figures,
            out_dir=out_dir,
            page_numbers=page_numbers,
            rotate_mode=args.rotate_mode,
            rotate_pages=parse_rotate_pages(args.rotate_pages),
            rotate_degrees=args.rotate_degrees,
            rotate_fallback=args.rotate_fallback,
        )
        save_outputs(
            out_dir,
            doc_result,
            preview_md,
            save_risk_chunks=not args.no_risk_chunks,
        )


if __name__ == "__main__":
    main()
