from __future__ import annotations

MARKET_SKILL_PRESETS = {
    "market_macro": {"module": "macro", "label": "宏观市场", "required": True},
    "market_industry": {"module": "industry", "label": "行业表现", "required": True},
    "market_ipo_heat": {"module": "ipo_market", "label": "IPO市场热度", "required": True},
    "market_sentiment_news": {"module": "public_opinion", "label": "公司舆情", "required": False},
}


