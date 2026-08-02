"""market 数据工程全局配置。

所有 fetch_* / build_* 脚本共用：路径、日期范围、IPO 宇宙引用。
评测环境无外网：fetch_* 只在开发机运行，运行时代码只读 data/ 下的本地 CSV。
"""
from pathlib import Path

MARKET_DIR = Path(__file__).resolve().parent
IPOI_DIR = MARKET_DIR.parent

# ---- 输入（赛题 + 万得补充 + 既有分析产物）----
DATASET_DIR = IPOI_DIR / "dataset"
EOD_CSV = DATASET_DIR / "hkshareeodprices.csv"
EDE_XLSX = DATASET_DIR / "EDE20260715.xlsx"
# EDE 瘦身导出（证券代码/简称/上市日/概念板块/港股通纳入日等）
EDE_SLIM_CSV = IPOI_DIR / "dataset_analysis" / "output" / "wind_ede20260715_slim.csv"
# 565 家招股书 IPO 目录（含 PDF 元数据、EOD 首日、day1/5/20/60 收益）
IPO_CATALOG_CSV = IPOI_DIR / "dataset_analysis" / "output" / "ipo_catalog_with_metrics.csv"

# ---- 输出 ----
DATA_DIR = MARKET_DIR / "data"
MACRO_DIR = DATA_DIR / "external" / "macro"
NEWS_DIR = DATA_DIR / "external" / "news"
DERIVED_DIR = DATA_DIR / "derived"

# ---- 外采时间范围（上市前 60 交易日留缓冲）----
# 招股书宇宙按 PDF 归档年多为 2020–2025，但部分 2025 年末招股书实际
# 上市日在 2026 年初（EDE/EOD）；另有个别延期至 2026-06。外采与热度
# 日历须覆盖到 max(listing_date)，否则「上市日前一日」热度查找会整行 NaN。
FETCH_START = "2019-10-01"
FETCH_END = "2026-06-30"

# IPO 热度日表日历（自然日）；须 >= 全样本最大 listing_date
IPO_START = "2020-01-01"
IPO_END = "2026-06-30"

# 招股书文件名表（补全 company_display「待补全_*」）
PROSPECTUS_CSV = DATASET_DIR / "prospectus_filenames_2020_2025.csv"

# 马宝灵万得补充导出（原始）与清洗落盘
WIND_RAW_DIR = DATASET_DIR / "wind"
WIND_DIR = DATA_DIR / "external" / "wind"

# HSICS 一级行业 → 粗行业（Agent 沿用）+ 恒生综合行业指数代码
HSICS_L1_TO_COARSE = {
    "医疗保健业": "生物科技/医药",
    "资讯科技业": "TMT/互联网",
    "信息科技业": "TMT/互联网",
    "电讯业": "TMT/互联网",
    "非必需性消费": "消费/零售",
    "必需性消费": "消费/零售",
    "能源业": "新能源/汽车",
    "金融业": "金融",
    "地产建筑业": "地产/建筑",
    "工业": "工业/制造",
    "原材料业": "工业/制造",
    "公用事业": "其他",
    "综合企业": "其他",
}
HSICS_L1_TO_INDEX = {
    "医疗保健业": ("HSCIH.HI", "恒生综合行业指数-医疗保健业"),
    "资讯科技业": ("HSCIIT.HI", "恒生综合行业指数-信息科技业"),
    "信息科技业": ("HSCIIT.HI", "恒生综合行业指数-信息科技业"),
    "电讯业": ("HSCITC.HI", "恒生综合行业指数-电讯业"),
    "非必需性消费": ("HSCICD.HI", "恒生综合行业指数-非必需性消费"),
    "必需性消费": ("HSCICS.HI", "恒生综合行业指数-必需性消费"),
    "能源业": ("HSCIEN.HI", "恒生综合行业指数-能源业"),
    "金融业": ("HSCIFN.HI", "恒生综合行业指数-金融业"),
    "地产建筑业": ("HSCIPC.HI", "恒生综合行业指数-地产建筑业"),
    "工业": ("HSCIIN.HI", "恒生综合行业指数-工业"),
    "原材料业": ("HSCIMT.HI", "恒生综合行业指数-原材料业"),
    "公用事业": ("HSCIUT.HI", "恒生综合行业指数-公用事业"),
    "综合企业": ("HSCICO.HI", "恒生综合行业指数-综合企业"),
}
# 板块净流入列名（港交所/HS）→ HSICS L1
HS_FLOW_L1 = {
    "能源业": "能源业",
    "原材料业": "原材料业",
    "工业": "工业",
    "非必需性消费": "非必需性消费",
    "必需性消费": "必需性消费",
    "医疗保健业": "医疗保健业",
    "电讯业": "电讯业",
    "公用事业": "公用事业",
    "金融业": "金融业",
    "地产建筑业": "地产建筑业",
    "资讯科技业": "资讯科技业",
    "综合企业": "综合企业",
}

# 收益/破发基准：近年发行价缺失，统一用首日开盘价（报告结论）
RETURN_BASE = "day0_open"

# 滚动窗口（交易日近似：30/90 自然日按原文档口径用自然日）
IPO_HEAT_WINDOWS_DAYS = [30, 90]

# EDE 概念 -> 粗行业 映射规则（首个命中生效，顺序即优先级）
INDUSTRY_RULES = [
    ("生物科技/医药", ["未盈利生物科技", "创新药", "生物医疗", "医疗器械", "CXO",
                     "抗肿瘤", "医疗耗材", "中资医疗", "互联网医疗", "智能医疗", "健康产业"]),
    ("TMT/互联网", ["互联网", "短视频", "AIGC", "人工智能", "网络科技", "移动互联网",
                   "ChatGPT", "DeepSeek", "直播", "基础大模型", "软件", "SAAS", "云计算",
                   "半导体", "芯片", "电子", "5G", "游戏", "文化传媒", "影视传媒"]),
    ("消费/零售", ["食品", "餐饮", "品牌服饰", "零售", "白酒", "谷子经济", "啤酒",
                  "乳业", "宠物", "美妆", "免税", "香港本地消费", "新型烟草"]),
    ("新能源/汽车", ["新能源", "锂电池", "光伏", "储能", "智能电网", "汽车", "氢能源"]),
    ("地产/建筑", ["内地房地产", "蓝筹地产", "物业", "建筑", "房地产信托", "基建"]),
    ("金融", ["银行", "保险", "券商", "财产管理", "金融科技", "互联网金融", "互联网信贷"]),
    ("工业/制造", ["高端装备", "机器人", "智能制造", "工业", "军工", "智能物流", "航运", "有色", "钢铁"]),
    ("教育/服务", ["教育", "在线教育", "人力资源", "现代服务"]),
]
INDUSTRY_FALLBACK = "其他"

# 粗行业 -> 恒生官方/准官方板块指数（AKShare 新浪可免费拉日线）
# 无官方细行业指数的行业（生科/消费/新能源等）保持不映射，继续用概念篮子 ind_ret_*
HS_SECTOR_INDEX = {
    "金融": "hsmbi",        # Hang Seng Mainland Banks Index
    "地产/建筑": "hsmpi",   # Hang Seng Mainland Properties Index
    "TMT/互联网": "hstech", # Hang Seng TECH Index
}
# HSMOGI（内地油气）一并落盘供对照，但不自动映射到「新能源/汽车」（语义差过大）

def ensure_dirs():
    for d in (MACRO_DIR, NEWS_DIR, DERIVED_DIR, WIND_DIR):
        d.mkdir(parents=True, exist_ok=True)


def write_sidecar(csv_path, source, note="", extra=None):
    """给每个落盘 CSV 写 sidecar JSON：来源、抓取时间、行数、日期范围。"""
    import json
    from datetime import datetime
    import pandas as pd

    csv_path = Path(csv_path)
    df = pd.read_csv(csv_path)
    date_col = next((c for c in df.columns if c.lower() in
                     ("date", "trade_dt", "日期", "trade_date")), None)
    meta = {
        "file": csv_path.name,
        "source": source,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "rows": int(len(df)),
        "columns": list(df.columns),
        "date_min": str(df[date_col].min()) if date_col else None,
        "date_max": str(df[date_col].max()) if date_col else None,
        "note": note,
    }
    if extra:
        meta.update(extra)
    sidecar = csv_path.with_suffix(".meta.json")
    sidecar.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta
