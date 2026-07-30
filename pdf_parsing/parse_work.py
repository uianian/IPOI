import json
import os
import sys
import torch
from pathlib import Path
from PIL import Image
from transformers import AutoModelForImageTextToText, AutoProcessor
from qwen_vl_utils import process_vision_info

MODEL_NAME = "./models/infly/Infinity-Parser2-Flash"

PARSE_PROMPT = """- Extract layout information from the provided PDF image.
- For each layout element, output its bbox, category, and the text content within the bbox.
- Bbox format: [x1, y1, x2, y2].
- Allowed layout categories: ['header', 'title', 'text', 'figure', 'table', 'formula', 'figure_caption', 'table_caption', 'page_footnote', 'footer'].
- Output as JSON array. Each element: {"bbox": [...], "category": "...", "text": "..."}
- For tables, convert to markdown table format inside the text field.
- Preserve reading order."""

RISK_KEYWORDS = [
    "風險因素", "對賭", "贖回", "關聯交易", "現金消耗",
    "重大不確定", "核心管線", "虧損", "訴訟", "質押",
    "风险因素", "对赌", "赎回", "关联交易", "现金消耗",
]

def load_model(gpu_id: int):
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
    model = AutoModelForImageTextToText.from_pretrained(
        MODEL_NAME,
        torch_dtype=torch.bfloat16,
        device_map="cuda:0",  # CUDA_VISIBLE_DEVICES已限定，始终是0
        trust_remote_code=True,
    )
    processor = AutoProcessor.from_pretrained(MODEL_NAME, trust_remote_code=True)
    return model, processor

def parse_page(model, processor, pil_image: Image.Image) -> list:
    messages = [{
        "role": "user",
        "content": [
            {"type": "image", "image": pil_image,
             "min_pixels": 2048, "max_pixels": 4096 * 4096},
            {"type": "text", "text": PARSE_PROMPT},
        ],
    }]
    text = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    image_inputs, video_inputs = process_vision_info(messages)
    inputs = processor(
        text=[text], images=image_inputs,
        videos=video_inputs, return_tensors="pt"
    ).to(model.device)

    with torch.no_grad():
        output_ids = model.generate(**inputs, max_new_tokens=4096, do_sample=False)

    generated = output_ids[:, inputs["input_ids"].shape[1]:]
    result_text = processor.batch_decode(
        generated, skip_special_tokens=True
    )[0]

    try:
        if "```" in result_text:
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
        return json.loads(result_text.strip())
    except json.JSONDecodeError:
        return [{"bbox": [], "category": "text", "text": result_text}]

def parse_pdf(model, processor, pdf_path: str, dpi: int = 150) -> list:
    from pdf2image import convert_from_path
    pages = convert_from_path(pdf_path, dpi=dpi)
    doc_result = []
    for i, page_img in enumerate(pages):
        print(f"  [GPU {os.environ['CUDA_VISIBLE_DEVICES']}] "
              f"{Path(pdf_path).name} {i+1}/{len(pages)}", flush=True)
        elements = parse_page(model, processor, page_img)
        doc_result.append({"page": i + 1, "elements": elements})
    return doc_result

def extract_risk_chunks(doc_result: list) -> list:
    chunks = []
    for page_data in doc_result:
        page_num = page_data["page"]
        for elem in page_data["elements"]:
            category = elem.get("category", "")
            text = elem.get("text", "")
            bbox = elem.get("bbox", [])
            if category == "table":
                chunks.append({"page": page_num, "bbox": bbox,
                               "type": "table", "content": text,
                               "source_tag": f"p{page_num}_table"})
            elif category in ("text", "title") and \
                 any(kw in text for kw in RISK_KEYWORDS):
                chunks.append({"page": page_num, "bbox": bbox,
                               "type": "text", "content": text,
                               "source_tag": f"p{page_num}_text"})
    return chunks

def process_file(gpu_id: int, pdf_path: str, out_dir: str):
    model, processor = load_model(gpu_id)
    out = Path(out_dir) / Path(pdf_path).stem
    out.mkdir(parents=True, exist_ok=True)

    # 断点续跑：已完成的跳过
    done_flag = out / "done.flag"
    if done_flag.exists():
        print(f"[跳过] {pdf_path} 已处理完成")
        return

    doc_result = parse_pdf(model, processor, pdf_path)

    with open(out / "full_parse.json", "w", encoding="utf-8") as f:
        json.dump(doc_result, f, ensure_ascii=False, indent=2)

    chunks = extract_risk_chunks(doc_result)
    with open(out / "risk_chunks.json", "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    done_flag.touch()  # 写完成标记
    print(f"[完成] GPU{gpu_id} {pdf_path} → {len(chunks)} chunks")

if __name__ == "__main__":
    # 用法: python parse_worker.py <gpu_id> <pdf_path> <out_dir>
    gpu_id  = int(sys.argv[1])
    pdf_path = sys.argv[2]
    out_dir  = sys.argv[3]
    process_file(gpu_id, pdf_path, out_dir)