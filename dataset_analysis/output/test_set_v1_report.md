# 测试集 test_set_v1 报告

> random_state=42；N=48

## 摘要

- 家数：**48**（目标 48）
- holdout：**42**（目标 ≥24）
- dev_seen：**6**
- 生科配额（18a_unprofit∪biotech_pharma）：**15**（目标 ≥15）
- 最大恒生一级：`医疗保健业` = **37.5%**（目标 ≤40%）
- 解析复用 / 待解析 / 缺失：21 / 27 / 0

## 年份 × 表现

| list_year | 平稳 | 暴涨 | 暴跌 | 破发/走弱 |
|---|---|---|---|---|
| 2020 | 2 | 2 | 2 | 2 |
| 2021 | 2 | 2 | 2 | 2 |
| 2022 | 2 | 2 | 2 | 2 |
| 2023 | 2 | 2 | 2 | 2 |
| 2024 | 2 | 2 | 2 | 2 |
| 2025 | 2 | 2 | 2 | 2 |

## 复用来源

new        27
samples    15
18a         6

## eval_role

holdout     42
dev_seen     6

## issuer_bucket

general             30
18a_unprofit         9
biotech_pharma       6
healthcare_other     3

## 恒生一级行业

医疗保健业     18
地产建筑业      7
资讯科技业      5
非必需性消费     5
必需性消费      4
工业         4
金融业        3
能源业        2

## 相对全库（有行情子集）占比差（示意）

### 年份

2020   -0.077
2021    0.010
2022    0.017
2023    0.053
2024    0.035
2025   -0.039

### 表现

平稳      -0.209
暴涨       0.136
暴跌       0.064
破发/走弱    0.009

## 样本清单

| 代码 | 简称 | 年 | 表现 | HS一级 | bucket | source | role | parse |
|------|------|----|------|--------|--------|--------|------|-------|
| 02126 | 药明巨诺-B | 2020 | 平稳 | 医疗保健业 | 18a_unprofit | samples | holdout | reuse_samples |
| 09926 | 康方生物 | 2020 | 平稳 | 医疗保健业 | biotech_pharma | 18a | dev_seen | reuse_18a |
| 06618 | 京东健康 | 2020 | 暴涨 | 医疗保健业 | biotech_pharma | new | holdout | need_parse |
| 09995 | 荣昌生物 | 2020 | 暴涨 | 医疗保健业 | biotech_pharma | 18a | dev_seen | reuse_18a |
| 01477 | 欧康维视生物-B | 2020 | 暴跌 | 医疗保健业 | 18a_unprofit | 18a | dev_seen | reuse_18a |
| 09939 | 开拓药业-B | 2020 | 暴跌 | 医疗保健业 | 18a_unprofit | 18a | dev_seen | reuse_18a |
| 01643 | 现代中药集团 | 2020 | 破发/走弱 | 医疗保健业 | biotech_pharma | samples | holdout | reuse_samples |
| 03347 | 泰格医药 | 2020 | 破发/走弱 | 医疗保健业 | biotech_pharma | samples | holdout | reuse_samples |
| 02137 | 腾盛博药-B | 2021 | 平稳 | 医疗保健业 | 18a_unprofit | new | holdout | need_parse |
| 02257 | 圣诺医药-B | 2021 | 平稳 | 医疗保健业 | 18a_unprofit | new | holdout | need_parse |
| 02155 | 森松国际 | 2021 | 暴涨 | 工业 | general | new | holdout | need_parse |
| 02161 | 健倍苗苗 | 2021 | 暴涨 | 医疗保健业 | biotech_pharma | new | holdout | need_parse |
| 02197 | 三叶草生物-B | 2021 | 暴跌 | 医疗保健业 | 18a_unprofit | 18a | dev_seen | reuse_18a |
| 06622 | 兆科眼科-B | 2021 | 暴跌 | 医疗保健业 | 18a_unprofit | 18a | dev_seen | reuse_18a |
| 01228 | 北海康成-B | 2021 | 破发/走弱 | 医疗保健业 | 18a_unprofit | new | holdout | need_parse |
| 02160 | 微创心通-B | 2021 | 破发/走弱 | 医疗保健业 | 18a_unprofit | new | holdout | need_parse |
| 02407 | 高视医疗 | 2022 | 平稳 | 医疗保健业 | healthcare_other | new | holdout | need_parse |
| 02459 | 升能集团 | 2022 | 平稳 | 工业 | general | new | holdout | need_parse |
| 01880 | 中国中免 | 2022 | 暴涨 | 非必需性消费 | general | new | holdout | need_parse |
| 02370 | 力高健康生活 | 2022 | 暴涨 | 地产建筑业 | general | new | holdout | need_parse |
| 02121 | 创新奇智 | 2022 | 暴跌 | 资讯科技业 | general | samples | holdout | reuse_samples |
| 06963 | 阳光保险 | 2022 | 暴跌 | 金融业 | general | new | holdout | need_parse |
| 01406 | 清晰医疗 | 2022 | 破发/走弱 | 医疗保健业 | healthcare_other | samples | holdout | reuse_samples |
| 01407 | 交运燃气 | 2022 | 破发/走弱 | 能源业 | general | new | holdout | need_parse |
| 02482 | 维天运通 | 2023 | 平稳 | 工业 | general | samples | holdout | reuse_samples |
| 09636 | 九方智投控股 | 2023 | 平稳 | 资讯科技业 | general | samples | holdout | reuse_samples |
| 02442 | 怡俊集团控股 | 2023 | 暴涨 | 地产建筑业 | general | new | holdout | need_parse |
| 02453 | 美中嘉和 | 2023 | 暴涨 | 医疗保健业 | healthcare_other | new | holdout | need_parse |
| 01973 | 天图投资 | 2023 | 暴跌 | 金融业 | general | new | holdout | need_parse |
| 02433 | 中天湖南集团 | 2023 | 暴跌 | 地产建筑业 | general | new | holdout | need_parse |
| 02271 | 众安智慧生活 | 2023 | 破发/走弱 | 地产建筑业 | general | new | holdout | need_parse |
| 09663 | 国鸿氢能 | 2023 | 破发/走弱 | 工业 | general | new | holdout | need_parse |
| 02535 | 泓基集团 | 2024 | 平稳 | 地产建筑业 | general | samples | holdout | reuse_samples |
| 02571 | 赛目科技 | 2024 | 平稳 | 资讯科技业 | general | new | holdout | need_parse |
| 02531 | 广联科技控股 | 2024 | 暴涨 | 资讯科技业 | general | new | holdout | need_parse |
| 02540 | 乐思集团 | 2024 | 暴涨 | 非必需性消费 | general | samples | holdout | reuse_samples |
| 01354 | 经发物业 | 2024 | 暴跌 | 地产建筑业 | general | new | holdout | need_parse |
| 02443 | 汽车街 | 2024 | 暴跌 | 非必需性消费 | general | new | holdout | need_parse |
| 00325 | 布鲁可 | 2024 | 破发/走弱 | 非必需性消费 | general | new | holdout | need_parse |
| 01334 | 瑞昌国际控股 | 2024 | 破发/走弱 | 能源业 | general | new | holdout | need_parse |
| 01364 | 古茗 | 2025 | 平稳 | 必需性消费 | general | samples | holdout | reuse_samples |
| 01828 | 富卫集团 | 2025 | 平稳 | 金融业 | general | samples | holdout | reuse_samples |
| 01384 | 滴普科技 | 2025 | 暴涨 | 资讯科技业 | general | samples | holdout | reuse_samples |
| 02097 | 蜜雪集团 | 2025 | 暴涨 | 必需性消费 | general | samples | holdout | reuse_samples |
| 01641 | 红星冷链 | 2025 | 暴跌 | 地产建筑业 | general | new | holdout | need_parse |
| 02589 | 沪上阿姨 | 2025 | 暴跌 | 必需性消费 | general | samples | holdout | reuse_samples |
| 02603 | 吉宏股份 | 2025 | 破发/走弱 | 非必需性消费 | general | new | holdout | need_parse |
| 03288 | 海天味业 | 2025 | 破发/走弱 | 必需性消费 | general | samples | holdout | reuse_samples |

## 使用说明

- 赛题硬指标（≥80% / ≥85%）默认只在 `eval_role=holdout` 上计算。
- `dev_seen`（多为 18a 调试池）仅作附表对照。
- PDF：`dataset/test/`；解析复用见 `test_set_v1_parse_plan.md`。
- **不可**将本测试集比例直接外推为 565 家总体均值。
