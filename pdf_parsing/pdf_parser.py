#!/usr/bin/env python3
"""
PDF 解析器：基于 Infinity-Parser2-Flash + Transformers 后端。

对齐官方 infinity_parser2 的关键行为：
  - PyMuPDF 渲染（默认 300 DPI）
  - 页级 batch 推理（默认 batch_size=4）
  - 官方后处理（JSON 提取 / 截断修复 / bbox 归一化还原 / JSON→MD）
  - do_resize=False + image_patch_size=16
  - max_new_tokens=32768

GPU 资源说明（当前服务器 8×RTX 3090 24GB）：
  - device_map="auto" 会将模型自动切分到可见 GPU；Flash 体量较小，通常 1 卡即可承载权重。
  - batch_size=4 且 max_new_tokens=32768 时，生成阶段 KV cache 占用很大，可能出现 OOM。
    若遇 OOM，请降低 --batch-size（如 1~2）或 --max-new-tokens（如 8192）。
  - 官方默认 vLLM 引擎 + 张量并行在本脚本中未启用（需额外安装 vLLM）；
    如需 vLLM 批量加速，请另行协商。
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
from pathlib import Path
from typing import List, Optional, Union

import torch
from PIL import Image
from qwen_vl_utils import process_vision_info
from transformers import AutoModelForImageTextToText, AutoProcessor

# ── 复用本地官方后处理工具（绕过包 __init__，避免拉取 vLLM 等重依赖）──
_INF_UTILS_PATH = (
    Path(__file__).resolve().parent
    / "INF-MLLM" / "Infinity-Parser2" / "infinity_parser2" / "utils" / "utils.py"
)
if not _INF_UTILS_PATH.is_file():
    raise ImportError(f"找不到官方后处理模块: {_INF_UTILS_PATH}")

_spec = importlib.util.spec_from_file_location("_inf_postprocess", _INF_UTILS_PATH)
_inf_postprocess = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_inf_postprocess)
convert_json_to_markdown = _inf_postprocess.convert_json_to_markdown
postprocess_doc2json_result = _inf_postprocess.postprocess_doc2json_result


def convert_pdf_to_images(pdf_path: Union[str, Path], dpi: int = 300) -> List[Image.Image]:
    """PyMuPDF 渲染 PDF 各页（与官方 infinity_parser2/utils/pdf.py 一致）。"""
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise ImportError(
            "PyMuPDF 未安装，请执行: pip install pymupdf"
        ) from e

    Image.MAX_IMAGE_PIXELS = None
    doc = fitz.open(str(pdf_path))
    images: List[Image.Image] = []
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    for page_num in range(len(doc)):
        pix = doc[page_num].get_pixmap(matrix=mat, alpha=False)
        images.append(Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB"))
    doc.close()
    return images

# ── 模型与推理默认参数 ─────────────────────────────────────
DEFAULT_MODEL = "./models/infly/Infinity-Parser2-Flash"
DEFAULT_DPI = 300
DEFAULT_BATCH_SIZE = 4
DEFAULT_MAX_NEW_TOKENS = 32768
MIN_PIXELS = 2048
MAX_PIXELS = 16777216  # 4096 * 4096

# 在官方 PROMPT_DOC2JSON 基础上：增加 figure_footnote / table_footnote，不含 formula_caption
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


# ── PDF 渲染（PyMuPDF，速度优先的页面级旋转校正）────────────
def render_pdf_pages(pdf_path: Union[str, Path], dpi: int = DEFAULT_DPI) -> List[Image.Image]:
    """
    将 PDF 各页渲染为 PIL Image。

    旋转处理（速度优先）：
      PyMuPDF 的 get_pixmap() 会自动应用 PDF 页面级 /Rotate 元数据（90/180/270°），
      无需额外的 OpenCV 检测。页内局部旋转内容不在此处理范围（与官方已知局限一致）。
    """
    return convert_pdf_to_images(str(pdf_path), dpi=dpi)


# ── 模型加载 ───────────────────────────────────────────────
def load_model(model_name: str = DEFAULT_MODEL, device_map: str = "auto"):
    model = AutoModelForImageTextToText.from_pretrained(
        model_name,
        torch_dtype=torch.bfloat16,
        device_map=device_map,
        trust_remote_code=True,
    )
    processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=True)
    return model, processor


# ── 批量推理（对齐官方 TransformersBackend）────────────────
def parse_pages_batch(
    page_images: List[Image.Image],
    model,
    processor,
    prompt: str = PARSE_PROMPT,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
) -> List[str]:
    """对多页图片做 batch 推理，返回每页原始模型输出文本。"""
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

        chat_template_kwargs = {"enable_thinking": False}
        text = processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            **chat_template_kwargs,
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

        with torch.no_grad():
            generated_ids = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=0.0,
                top_p=1.0,
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

    return results


# ── 后处理：官方 pipeline + 结构化 elements ────────────────
def postprocess_page(raw_text: str, page_image: Image.Image) -> List[dict]:
    """单页后处理，返回带像素坐标 bbox 的 elements 列表。"""
    json_str = postprocess_doc2json_result(
        raw_text, page_image, output_format="json"
    )
    try:
        elements = json.loads(json_str)
        if isinstance(elements, list):
            return elements
    except json.JSONDecodeError:
        pass
    return [{"bbox": [], "category": "text", "text": raw_text}]


def page_to_markdown(elements: List[dict]) -> str:
    """将单页 elements 转为 Markdown（官方 convert_json_to_markdown 逻辑）。"""
    return convert_json_to_markdown(json.dumps(elements, ensure_ascii=False))


# ── Figure 裁剪保存 ────────────────────────────────────────
def save_figure_crops(
    page_image: Image.Image,
    elements: List[dict],
    page_num: int,
    figures_dir: Path,
    out_dir: Path,
) -> None:
    """根据 figure bbox 从页面图裁剪并保存，回写 image_path 字段。"""
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
        elem["image_path"] = str(crop_path.relative_to(out_dir))


# ── 整份 PDF 解析 ──────────────────────────────────────────
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
) -> tuple[List[dict], str]:
    """
    解析整份 PDF。

    Returns:
        doc_result: [{"page": int, "elements": [...]}, ...]
        full_markdown: 全文 Markdown（页间双换行分隔）
    """
    pdf_path = Path(pdf_path)
    print(f"正在渲染 PDF: {pdf_path} (PyMuPDF, {dpi} DPI)")
    page_images = render_pdf_pages(pdf_path, dpi=dpi)
    print(f"共 {len(page_images)} 页，batch_size={batch_size}，开始推理...")

    raw_outputs = parse_pages_batch(
        page_images,
        model,
        processor,
        batch_size=batch_size,
        max_new_tokens=max_new_tokens,
    )

    doc_result: List[dict] = []
    md_pages: List[str] = []

    if out_dir is None:
        out_dir = Path("output") / pdf_path.stem
    if figures_dir is None:
        figures_dir = out_dir / "figures"

    for i, (page_img, raw_text) in enumerate(zip(page_images, raw_outputs)):
        page_num = i + 1
        elements = postprocess_page(raw_text, page_img)

        if save_figures:
            save_figure_crops(page_img, elements, page_num, figures_dir, out_dir)

        doc_result.append({"page": page_num, "elements": elements})
        md_pages.append(page_to_markdown(elements))

    full_markdown = "\n\n".join(md_pages)
    print(f"完成：{pdf_path}")
    return doc_result, full_markdown


# ── 输出写入 ───────────────────────────────────────────────
def save_outputs(
    out_dir: Path,
    doc_result: List[dict],
    full_markdown: str,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    full_json_path = out_dir / "full_parse.json"
    with open(full_json_path, "w", encoding="utf-8") as f:
        json.dump(doc_result, f, ensure_ascii=False, indent=2)

    result_md_path = out_dir / "result.md"
    with open(result_md_path, "w", encoding="utf-8") as f:
        f.write(full_markdown)

    print(f"完整 JSON: {full_json_path}")
    print(f"Markdown:  {result_md_path}")


# ── CLI ────────────────────────────────────────────────────
def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Infinity-Parser2-Flash PDF 解析（官方对齐版）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "input",
        help="PDF 文件路径，或包含 *.pdf 的目录",
    )
    p.add_argument(
        "-o", "--output-dir",
        default=None,
        help="输出根目录，默认 output/<pdf_stem>/",
    )
    p.add_argument("--model", default=DEFAULT_MODEL, help="模型路径或 HF ID")
    p.add_argument("--dpi", type=int, default=DEFAULT_DPI, help="PyMuPDF 渲染 DPI")
    p.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
        help="页级 batch 大小；OOM 时请降为 1~2",
    )
    p.add_argument(
        "--max-new-tokens", type=int, default=DEFAULT_MAX_NEW_TOKENS,
        help="生成 token 上限；与官方一致为 32768，显存不足时可降低",
    )
    p.add_argument(
        "--no-figures", action="store_true",
        help="不裁剪保存 figure 图片",
    )
    p.add_argument(
        "--device-map", default="auto",
        help='模型 device_map，官方 Transformers 后端默认 "auto"',
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
        doc_result, full_md = parse_pdf(
            pdf_path,
            model,
            processor,
            dpi=args.dpi,
            batch_size=args.batch_size,
            max_new_tokens=args.max_new_tokens,
            save_figures=not args.no_figures,
            out_dir=out_dir,
        )
        save_outputs(out_dir, doc_result, full_md)


if __name__ == "__main__":
    main()
