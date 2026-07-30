"""将模型英文 reasoning 译为「繁体中文为主、英文术语保留」的混合展示文案。"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")

_TRANSLATE_SYSTEM = """你是港股 IPO 風險分析助手的「思考過程翻譯器」。
任務：把模型內部英文 reasoning 譯成前端可直接展示的文案。

輸出要求：
1. 以繁體中文為主，完整傳達原意（不要摘要成一句話）。
2. 英文混合：工具名、字段編碼、API/函數名、風險代碼、數字單位、專有名詞保留英文；
   關鍵概念可用「中文（English）」形式，例如「現金跑道（cash runway）」「未盈利（unprofitable）」。
3. 只輸出譯文本身，不要加「譯文：」「以下是翻譯」等前後綴，不要 Markdown 標題。
4. 保持原有段落/條列結構；不要臆造原文沒有的結論。"""


def mostly_english(text: str) -> bool:
    if not text or not text.strip():
        return False
    cjk = len(_CJK_RE.findall(text))
    latin = len(_LATIN_RE.findall(text))
    if latin == 0:
        return False
    return latin >= max(12, cjk * 2)


def _strip_fence(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:\w+)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


async def translate_think_to_hant_mixed(llm: Any, reasoning: str) -> str:
    """英 → 繁体中文+英文术语混合。失败时抛错由调用方兜底。"""
    text = (reasoning or "").strip()
    if not text:
        return ""
    if not mostly_english(text):
        try:
            import zhconv

            return zhconv.convert(text, "zh-hant")
        except Exception:
            return text

    # 过长时截断，避免翻译拖垮主链路
    src = text if len(text) <= 2500 else text[:2500] + "…"
    messages = [
        {"role": "system", "content": _TRANSLATE_SYSTEM},
        {
            "role": "user",
            "content": f"請翻譯以下英文思考過程：\n\n{src}",
        },
    ]
    result = await llm.chat_completion(
        messages,
        temperature=0.0,
        enable_reasoning=False,
        max_tokens=min(1200, max(256, len(src) // 2 + 200)),
    )
    out = _strip_fence(result.get("content") or "")
    if not out:
        raise RuntimeError("empty think translation")
    try:
        import zhconv

        out = zhconv.convert(out, "zh-hant")
    except Exception:
        pass
    return out
