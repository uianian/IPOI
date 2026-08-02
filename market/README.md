# market — 市场情绪指标数据工程

对照《市场情绪agent实现背景材料》与《市场情绪指标_赛题数据覆盖与外采研究报告》，
把市场情绪 Agent 所需数据逐指标落地为本地 CSV：外采数据一次性抓取落盘，
本地可算指标从赛题 EOD + 万得 EDE 构建。**评测环境无外网，运行时只读本地文件。**

**交给市场情绪 Agent 同学（周杰）的使用说明**：  
[`市场情绪数据使用报告_交接周杰.md`](市场情绪数据使用报告_交接周杰.md)
（质量、缺失与替换、来源复现、优先公司、舆情建议、脚本位置）。

**交给指标定义同学（马宝灵）的外采补充**：  
[`市场情绪指标外采补充报告_交接马宝灵.md`](市场情绪指标外采补充报告_交接马宝灵.md)
（逐项采集成败、不足与原因、万得待下载清单）。

## 快速开始

```bash
cd IPOI/market
# 环境（Python 3.10 venv，已建好；重建用下面两行）
python3.10 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 外采（仅开发机，需外网）— 免费源；权威序列已被万得覆盖的可跳过
.venv/bin/python scripts/fetch_macro_indices.py   # HSTECH/VHSI（HSI 已由万得替换）
.venv/bin/python scripts/fetch_hs_sector_indices.py
.venv/bin/python scripts/fetch_southbound.py
.venv/bin/python scripts/fetch_fed_dxy.py         # DFF；DXY 已由万得 USDX 替换
.venv/bin/python scripts/fetch_news.py
.venv/bin/python scripts/fetch_subscription_multiples.py

# 万得补充（马宝灵导出 → dataset/wind/，无需外网）
.venv/bin/python scripts/ingest_wind_exports.py   # 清洗并覆盖 HSI/DXY/US10Y/HSICS/认购等

# 本地构建（无需外网，依赖顺序如下）
.venv/bin/python scripts/build_market_turnover.py
.venv/bin/python scripts/build_industry_map.py      # HSICS 优先，EDE 概念兜底
.venv/bin/python scripts/build_industry_baskets.py
.venv/bin/python scripts/build_ipo_market_heat.py
.venv/bin/python scripts/build_sentiment_features.py
.venv/bin/python scripts/merge_subscription_into_features.py  # 致富 + 万得网上/网下

# 体检
.venv/bin/python scripts/check_coverage.py
.venv/bin/python scripts/analyze_sentiment_completeness.py
```

外采/热度日历上界见 `config.FETCH_END` / `IPO_END`（当前 **2026-06-30**）。  
万得原始包：`../dataset/wind/`；清洗落盘：`data/external/wind/` + 覆盖部分 `data/external/macro/`。

## 指标 ↔ 数据文件映射（对照原文档）

### 模块1 宏观市场（走势30% / 流动性40% / 波动率20% / 外部环境10%）

| 原文档指标 | 数据文件 | 特征列（宽表） | 说明 |
|-----------|----------|----------------|------|
| 恒指前5/20/60日收益 | `external/macro/hsi.csv` | `hsi_ret_*` | **万得 HSI.HI**（`ingest_wind_exports`）；旧 AKShare 备份 `hsi_akshare_backup.csv` |
| 恒生科技前5/20/60日收益 | `external/macro/hstech.csv` | `hstech_ret_*` | AKShare；指数 2020-07 起 |
| 前20日港股平均成交额 | `derived/market_turnover_daily.csv` | `mkt_turnover_*` | 赛题 EOD 汇总 |
| 前20日南向资金变化 | `external/macro/southbound.csv` | `southbound_net_*` | 东财 |
| 恒指20日标准差 | 由 hsi.csv | `hsi_vol_20d` | |
| VHSI 前5日均值 | `external/macro/vhsi.csv` | `vhsi_avg_5d` | 约 2021-03 起；缺口用 `hsi_vol_20d` |
| 美联储利率 | `external/macro/fed_dff.csv` | `dff_level`, `dff_chg_30cd` | FRED |
| 美元指数 | `external/macro/dxy.csv` | `dxy_ret_20d` | **万得 USDX.FX（ICE）**；旧 FRED 代理备份 `dxy_fred_dtwexbgs_backup.csv` |
| 美债 10Y | `external/macro/us10y.csv` | `us10y_level`, `us10y_chg_20d` | **万得 G0000891** |

### 模块2 行业热度

| 原文档指标 | 数据文件 | 特征列 | 说明 |
|-----------|----------|--------|------|
| 行业分类 | `derived/ipo_industry_map.csv` | `industry`, `hsics_l1_name`, `industry_source` | **优先 HSICS 一级**（539/565）；EDE 概念兜底；「其他」约 **29** 家 |
| 行业指数 5/20/60 日收益 | `external/wind/hsics_index_daily.csv` | `ind_ret_*`, `hs_sector_ret_*`, `industry_return_source` | **恒生综合行业指数**（HSCIH/HSCIIT…）；无 HSICS 时回退概念篮子 |
| 相对恒指超额 | 计算列 | `ind_excess_20d`, `hs_sector_excess_20d` | |
| 行业创新高 / 成交额变化 | `derived/industry_basket_daily.csv` | `ind_newhigh_ratio`, `ind_amount_chg_20d` | 仍用概念成分聚合 |
| 行业板块净流入 | `external/wind/hs_sector_net_inflow_daily.csv` | `ind_net_inflow_20d` | 港交所 HS 分类；**约 2022-01 起有值**，此前视为缺失 |
| 行业 12 月 IPO 热度 | `derived/ipo_industry_heat_daily.csv` | `ind_ipo_count_365d` 等 | |
| 行业 ETF 净流入 / 换手 / 政策事件 | — | — | 仍未单独落地（净流入用板块资金近似） |

### 模块3 IPO 市场热度

| 原文档指标 | 数据文件 | 特征列 | 说明 |
|-----------|----------|--------|------|
| 近30/90天 IPO 数与收益/破发/回撤 | `derived/ipo_market_heat_daily.csv` | `ipo_count_*`, `avg_*`, `break_rate_60d`, `avg_mdd20_60d` | 收益基准仍为首日开盘（事件表）；宽表另有 `issue_price`（万得）供对照 |
| 超额认购 | 致富 CSV + 万得 | `subscription_multiple` | 致富优先；缺口可用万得网上倍数填 |
| 公开发售倍数 | 万得 `ipo_listing_stats.csv` | `public_offer_multiple` | 网上发行有效认购倍数 **537/565** |
| 国际配售/网下倍数 | 同上 | `international_placing_multiple` | 网下有效申购倍数 **520/565** |

### 模块4 舆情

| 原文档指标 | 数据文件 | 说明 |
|-----------|----------|------|
| 公司正负面新闻 | `external/news/{code}.csv` | 东财近期刊，**不能支撑 2020–2025 回测**；建议砍权重或招股书代理 |

## 最终交付：`derived/ipo_sentiment_features.csv`

565 家 × **约 62 列**（含 HSICS / us10y / 认购三件套 / issue_price / 净流入等）。  
`outcome_*` **仅验证用，禁止作特征**。缺失一律 NaN，不填 0。

抽样核验：`derived/sample_sentiment_completeness_report.md`。  
联调检索见 [`../retrieval/README.md`](../retrieval/README.md)。

## 数据质量分析（全量 565 家，接入万得后）

| 档位 | 家数 | 占比 | 含义 |
|------|------|------|------|
| 严格完整 | **394** | 69.7% | 主链路齐（含 VHSI+行业收益+新闻指针） |
| MVP可行 | **139** | 24.6% | 无硬缺口 |
| **最大可行** | **533** | **94.3%** | |
| 核心缺口 | **32** | 5.7% | |
| 推荐优先（行业≠其他） | **~536 可行中绝大多数** | — | HSICS 后「其他」仅 **29** 家 |

抽样 54 家：**严格完整 15**、MVP 34、核心缺口 5、最大可行 **49**；推荐优先 **49**（几乎全体可行样本行业已映射）。

### 分模块覆盖（接入万得后）

| 模块 | 齐备/非空 | 要点 |
|------|-----------|------|
| HSI / DXY / US10Y | ~100% | 万得权威序列 |
| VHSI | 73% | 仍受源起点限制 |
| 行业收益 `ind_ret_20d`（HSICS） | **539（95.4%）** | 原概念篮子仅 ~40% |
| 官方/`hs_sector_ret_20d` | **539（95.4%）** | 与 HSICS 对齐 |
| 板块净流入 20d | **331（58.6%）** | 2022 前无有效数据 |
| 认购超额 / 公开 / 网下 | **539 / 537 / 520** | 国配由 0 → 520 |
| 发行价 `issue_price` | **537** | 供对照；事件收益仍用开盘基准 |
| 舆情回测 | 不可用 | 同前 |

### 质量结论

1. 马宝灵万得包已消除原最大短板：**行业指数与分类、ICE DXY、美债、国配/公开发售**。  
2. 仍缺：舆情历史、完整 VHSI 早期、认购缺口 26 家（万得亦无）、02553 等无行情样本。  
3. Agent 优先用 `industry_return_source=hsics` 的行；看 `hsics_index_code` / `ind_ret_*`。

## 数据来源清单（核查用）

| 数据 | 来源 | 地址/路径 |
|------|------|-----------|
| **HSI / DXY / US10Y / HSICS / IPO 认购·发行价 / 板块净流入** | **万得终端导出** | `dataset/wind/*` → `scripts/ingest_wind_exports.py` |
| HSTECH/VHSI | AKShare 新浪 | https://akshare.akfamily.xyz/ |
| 南向资金 | AKShare 东财 | https://data.eastmoney.com/hsgt/ |
| 联储利率 DFF | FRED | https://fred.stlouisfed.org/series/DFF |
| 超额认购（主） | 致富证券 + 新股渔夫 | chiefgroup / xinguyufu |
| EOD 行情 | 赛题 `hkshareeodprices.csv` | — |
| EDE 概念（兜底） | `dataset/EDE20260715.xlsx` | — |

每个 CSV 均有同名 `.meta.json` sidecar：来源、抓取时间、行数、日期范围、备注。

## 已知限制

1. **招股书归档年 vs 上市日**：数据集文件夹按 2020–2025 招股书收集，上市日以 EDE/EOD 为准，可落在 2026；勿按 PDF 年份裁特征日历。
2. **认购倍数**：致富证券可覆盖大部分 2020–2025 IPO；新股渔夫完整历史需登录（未登录仅最近约30条）。缺口代码见 `data/external/ipo/subscription_missing_codes.txt`，可用披露易「分配结果/Allotment Results」公告半自动补齐（https://www.hkexnews.hk/）。
3. **新闻历史深度不足**：东财接口只有近期新闻，2020-2025 回测期为空。
4. **行业收益**：已用万得 **恒生综合行业指数（HSICS）** 作为主路径；概念篮子仅作金额/创新高与无 HSICS 时的收益兜底。
5. **HSTECH/VHSI 起点晚**：属指数本身发布时间/数据源限制。
6. **DXY / HSI**：已切换为万得权威序列；FRED DTWEXBGS / AKShare HSI 仅作备份文件保留。
7. **板块净流入**：万得注明 2021 及更早无数据，特征上 2022-01 前记缺失。
8. EDE 上市日错配（老股再发行等）仍用「与 EOD 首日差>30天回退」规则。
