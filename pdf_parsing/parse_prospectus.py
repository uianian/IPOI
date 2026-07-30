import json
import os
from pathlib import Path
from PIL import Image
import torch
from transformers import AutoModelForImageTextToText, AutoProcessor
from qwen_vl_utils import process_vision_info

# ── 加载模型 ──────────────────────────────────────────────
MODEL_NAME = "./models/infly/Infinity-Parser2-Flash"  # modelscope下载的本地路径

model = AutoModelForImageTextToText.from_pretrained(
    MODEL_NAME,
    torch_dtype=torch.bfloat16,
    device_map="auto",
    trust_remote_code=True,
)
processor = AutoProcessor.from_pretrained(MODEL_NAME, trust_remote_code=True)

# ── 解析单张图片 ──────────────────────────────────────────
PARSE_PROMPT = """- Extract layout information from the provided PDF image.
- For each layout element, output its bbox, category, and the text content within the bbox.
- Bbox format: [x1, y1, x2, y2].
- Allowed layout categories: ['header', 'title', 'text', 'figure', 'table', 'formula', 'figure_caption', 'table_caption', 'page_footnote', 'footer'].
- Output as JSON array. Each element: {"bbox": [...], "category": "...", "text": "..."}
- For tables, convert to markdown table format inside the text field.
- Preserve reading order."""

def parse_page(pil_image: Image.Image) -> list:
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "image": pil_image,
                    "min_pixels": 2048,
                    "max_pixels": 4096 * 4096,
                },
                {"type": "text", "text": PARSE_PROMPT},
            ],
        }
    ]

    text = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    image_inputs, video_inputs = process_vision_info(messages)
    inputs = processor(
        text=[text],
        images=image_inputs,
        videos=video_inputs,
        return_tensors="pt",
    ).to(model.device)

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=4096,
            do_sample=False,
        )

    # 只取新生成的token
    generated = output_ids[:, inputs["input_ids"].shape[1]:]
    result_text = processor.batch_decode(
        generated, skip_special_tokens=True, clean_up_tokenization_spaces=False
    )[0]

    # 解析JSON，容错处理
    try:
        # 有时模型会在JSON外加```json ... ```
        if "```" in result_text:
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
        return json.loads(result_text.strip())
    except json.JSONDecodeError:
        # 解析失败就返回原始文本，不丢页
        return [{"bbox": [], "category": "text", "text": result_text}]


# ── 处理整份PDF ───────────────────────────────────────────
def parse_pdf(pdf_path: str, dpi: int = 150) -> list:
    """
    返回列表，每个元素对应一页：
    {"page": 1, "elements": [...]}
    """
    from pdf2image import convert_from_path

    print(f"正在转换PDF: {pdf_path}")
    pages = convert_from_path(pdf_path, dpi=dpi)
    print(f"共 {len(pages)} 页，开始逐页解析...")

    doc_result = []
    for i, page_img in enumerate(pages):
        print(f"  解析第 {i+1}/{len(pages)} 页...", end="\r")
        elements = parse_page(page_img)
        doc_result.append({
            "page": i + 1,
            "elements": elements,
        })

    print(f"\n完成：{pdf_path}")
    return doc_result


# ── 提取风险相关内容（给RAG用）────────────────────────────
RISK_KEYWORDS = [
    "風險因素", "對賭", "贖回", "關聯交易", "現金消耗",
    "重大不確定", "核心管線", "虧損", "訴訟", "質押",
    "风险因素", "对赌", "赎回", "关联交易", "现金消耗",  # 简体兜底
]

def extract_risk_chunks(doc_result: list) -> list:
    """
    输出RAG友好的chunk列表，每个chunk带页码+bbox用于溯源
    """
    chunks = []
    for page_data in doc_result:
        page_num = page_data["page"]
        for elem in page_data["elements"]:
            category = elem.get("category", "")
            text = elem.get("text", "")
            bbox = elem.get("bbox", [])

            # 保留所有表格
            if category == "table":
                chunks.append({
                    "page": page_num,
                    "bbox": bbox,
                    "type": "table",
                    "content": text,
                    "source_tag": f"p{page_num}_table",
                })
            # 命中关键词的文本段
            elif category in ("text", "title") and \
                 any(kw in text for kw in RISK_KEYWORDS):
                chunks.append({
                    "page": page_num,
                    "bbox": bbox,
                    "type": "text",
                    "content": text,
                    "source_tag": f"p{page_num}_text",
                })

    return chunks


# ── 主流程 ────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    pdf_path = sys.argv[1] if len(sys.argv) > 1 else "prospectus.pdf"
    out_dir = Path("output") / Path(pdf_path).stem
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. 解析全文
    doc_result = parse_pdf(pdf_path)

    # 2. 保存完整JSON（含页码+bbox，供前端溯源）
    full_json_path = out_dir / "full_parse.json"
    with open(full_json_path, "w", encoding="utf-8") as f:
        json.dump(doc_result, f, ensure_ascii=False, indent=2)

    # 3. 提取风险chunks（供RAG入库）
    chunks = extract_risk_chunks(doc_result)
    chunks_path = out_dir / "risk_chunks.json"
    with open(chunks_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    print(f"完整解析: {full_json_path}")
    print(f"风险chunks: {chunks_path}（共 {len(chunks)} 条）")