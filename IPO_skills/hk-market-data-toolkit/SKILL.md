---
name: hk-market-data-toolkit
description: 查询、关联港股基本信息（hksharedescription证券概况、hkcompanyinfo公司信息）与历史行情（HKshareEODPrices）三张数据表，用于获取上市日期/发行价/行业等结构化信息、以及计算上市后N日涨跌幅、破发情况。当用户需要"查股票代码""上市日期""发行价""行业""历史行情""涨跌幅计算""破发验证"等结构化数据时使用本skill，而不是去解析PDF招股书（招股书解析请用 hk-ipo-pdf-parsing）。
---

# 港股基础数据集工具

供全组共用，服务于任务2市场情绪Agent的行情特征、任务3报告生成的"上市后表现验证"部分。

## 三张表

### 1. `hksharedescription.csv` — 证券概况表（803行，30列）

关键字段：
- `S_INFO_WINDCODE` / `S_INFO_CODE`：证券代码（关联行情表的主键）
- `S_INFO_NAME` / `S_INFO_NAME_ENG`：证券简称（中/英）
- `S_INFO_FULLNAME` / `S_INFO_FULLNAME_ENG`：全称
- `S_INFO_COMPCODE`：公司代码（关联 `hkcompanyinfo.csv` 的主键）
- `S_INFO_LISTBOARD`：上市板块
- `S_INFO_LISTDATE` / `S_INFO_DELISTDATE`：上市/退市日期（整数格式YYYYMMDD，
  使用前需转成日期类型）
- `S_INFO_LISTPRICE`：发行价（计算破发/涨跌幅的基准价）
- `S_INFO_STATUS`：证券状态
- `IS_H` / `IS_HKSC`：是否H股/港股通标记

### 2. `hkcompanyinfo.csv` — 公司信息表（4501行，25列）

关键字段：
- `S_INFO_COMPCODE`：公司代码（关联证券概况表）
- `S_INFO_COMPNAME` / `COMP_SNAME` / `COMP_NAME_ENG`：公司全称/简称/英文名
- `FOUNDDATE`：成立日期
- `BRIEFING`：公司简介（文本，可辅助行业/主营业务判断）
- `BUSINESSSCOPE` / `BUSINESSSCOPE_ENG`：经营范围
- `TOTALEMPLOYEES`：员工总数
- `REGCAPITAL`：注册资本

### 3. `HKshareEODPrices`（日行情表，需向命题方按赛程确认最终交付形式与字段）

用途：计算上市首日/5日/20日/60日涨跌幅。核心字段预期包含：证券代码、
交易日期、开盘价、收盘价、最高价、最低价、成交量、涨跌幅。**注意**：本skill
编写时该表的数据字典PDF无法正常解析（文件可能损坏或格式特殊），实际开发时
第一步应重新确认该文件可正常打开，并把真实字段名补全到本skill，不要凭猜测
字段名直接写入生产代码。

## 表关联关系

```
hkcompanyinfo.S_INFO_COMPCODE  ←→  hksharedescription.S_INFO_COMPCODE
hksharedescription.S_INFO_WINDCODE (或 S_INFO_CODE)  ←→  EOD行情表.证券代码
```

## 常用计算：上市后N日涨跌幅 / 是否破发

```python
import pandas as pd

share = pd.read_csv("hksharedescription.csv", encoding="cp1252")
# 上市日期是整数YYYYMMDD，需转换
share["list_date"] = pd.to_datetime(share["S_INFO_LISTDATE"], format="%Y%m%d", errors="coerce")

# 伪代码：拿到某只股票上市后N个交易日的行情，与发行价 S_INFO_LISTPRICE 比较
def pct_change_after_listing(code, n_trading_days, eod_df, listprice):
    prices = eod_df[eod_df["code"] == code].sort_values("trade_date")
    prices = prices[prices["trade_date"] >= listing_date]
    if len(prices) <= n_trading_days:
        return None  # 数据不足，不要硬算
    target_price = prices.iloc[n_trading_days]["close"]
    return (target_price - listprice) / listprice

# 是否破发：收盘价 < 发行价 即为破发
```

务必处理好编码问题：`hksharedescription.csv` 声明编码为 `cp1252`，
`hkcompanyinfo.csv` 声明编码为 `iso-8859-1`——虽然文件名和内容像是中文数据，
但读取时必须显式指定对应编码，直接用默认utf-8读取大概率乱码或报错。

## 数据不足/缺失时的处理原则

- 上市不足N个交易日的新股，对应"上市后N日涨跌幅"字段应为空值而不是0，
  避免下游模型把"数据缺失"误当成"零涨跌"参与训练/评估；
- 退市股票（`S_INFO_DELISTDATE`非空）在做长周期验证时需要特殊处理，
  不能默认所有股票都能取到60个交易日的数据。

## 输出后交给谁

- 行情特征 → 市场情绪Agent（`ipo-multi-agent-orchestration`）
- 上市后表现数据 → `ipo-warning-report-generator`（预警效力反向验证部分）
