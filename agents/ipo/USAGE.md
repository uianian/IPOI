
# 港股IPO多智能体风险预警系统 — 完整使用指南

## 一、快速开始（3步跑通）

### Step 1：配置 LLM

编辑 `configs/settings.yaml`：

**方式A：使用 OpenAI API（推荐，最简）**

```yaml
llm:
  provider: "openai"
  api_key: "sk-xxxxxxxxxxxxxxxx"                  # 你的 OpenAI API Key
  api_base: "https://api.openai.com/v1"           # 端点地址
  chat_model: "gpt-4o"                            # 对话模型
  embedding_model: "text-embedding-3-large"       # 向量模型
```

也可通过环境变量设置（优先级高于配置文件）：

```bash
export OPENAI_API_KEY="sk-xxxxxxxxxxxxxxxx"
export IPO_LLM_PROVIDER="openai"
export IPO_LLM_API_BASE="https://api.openai.com/v1"
export IPO_LLM_CHAT_MODEL="gpt-4o"
```

**方式B：使用 vLLM 本地部署**

```yaml
llm:
  provider: "vllm"
  vllm_base_url: "http://localhost:8000/v1"
  chat_model: "Qwen2.5-72B-Instruct"
  embedding_model: "BAAI/bge-large-zh-v1.5"
```

**方式C：使用其他 OpenAI 兼容 API**

```yaml
llm:
  provider: "openai"
  api_key: "your-api-key"
  api_base: "https://api.deepseek.com/v1"        # DeepSeek
  chat_model: "deepseek-chat"
  embedding_model: "text-embedding-3-large"       # 仍可用 OpenAI embedding
```

> **提示**：如果 Embedding 和 Chat 使用不同服务商，可以分别配置 `api_base` 和 `vllm_base_url`，系统会根据 provider 自动选择。

### Step 2：安装依赖

```bash
pip install -r requirements.txt
```

### Step 3：运行示例

```bash
python scripts/run_example.py
```

该脚本会：
1. 读取内置的示例招股书文本
2. 自动完成文档索引、多Agent分析、冲突检测、辩论、融合、报告生成
3. 在终端打印完整风险报告
4. 保存 JSON 到 `output_example.json`

---

## 二、输入格式说明

系统支持两种输入方式：

### 方式1：纯文本输入（推荐快速验证）

直接传入招股书文本字符串，系统会自动分片、索引、分析。

```python
from src.skills.base import SkillInput
from src.skills.long_doc_retrieval.skill import LongDocRetrievalSkill

doc_skill = LongDocRetrievalSkill(vllm_client)

# 索引文本
result = await doc_skill.execute(SkillInput(
    doc_id="my_doc_001",
    params={
        "action": "index_text",
        "text": "这里是招股书的完整文本内容...",  # 直接传入文本
    },
))
```

### 方式2：PDF 文件输入

```python
result = await doc_skill.execute(SkillInput(
    doc_id="my_doc_001",
    params={
        "action": "index",
        "file_path": "/data/prospectus/example.pdf",  # PDF 文件路径
    },
))
```

### 输入文本示例（完整版）

以下是 `scripts/run_example.py` 中内置的示例招股书文本，涵盖竞赛关注的核心风险要素：

```
公司概况

百奥赛图基因科技有限公司（以下简称"本公司"或"发行人"）是一家专注于基因编辑及抗体药物开发的生物科技公司，
注册于开曼群岛，通过VIE架构运营中国境内实体。公司尚未实现盈利，截至最近报告期，累计亏损约人民币18.5亿元。
公司计划在香港联交所主板上市，股票代码02315，发行价区间为每股15.60-16.80港元，拟发行约1.05亿股。

风险因素

1. 未盈利风险：本公司自成立以来持续亏损。截至2024年12月31日，公司年度经营性现金净流出约人民币5.2亿元，
现金及现金等价物余额约人民币6.8亿元。按照当前消耗速度，若无法获得额外融资，公司资金预计可在未来约15个月内耗尽。

2. VIE架构风险：本公司采用VIE架构运营中国境内业务，相关协议安排可能被中国监管机构认定为无效。

3. 核心管线进度风险：公司核心产品BIO-001目前处于II期临床试验阶段，距离商业化仍有较长时间。

4. 关联交易风险：本公司与控股股东关联方存在大额技术服务交易，2024年度关联交易金额约人民币1.2亿元，
占公司采购总额的35%。

5. 对赌与赎回条款：公司历史上多轮融资中签署了对赌协议及赎回条款，若公司未能在2025年6月30日前完成上市，
投资者有权要求公司以年化8%的回报率赎回股份。

6. 知识产权风险：公司核心专利正在被第三方提起无效宣告请求。

7. 客户集中度风险：公司前五大客户贡献了约62%的营业收入。

财务数据

项目                        2024年      2023年      2022年
营业收入（百万元）          328.5       215.3       142.7
毛利（百万元）              142.3       79.5        44.3
毛利率                      43.3%       36.9%       31.0%
研发费用（百万元）          285.6       238.4       195.2
净利润（百万元）            -512.3      -438.7      -365.2
经营性现金流净额（百万元）  -518.5      -426.3      -342.8
现金及等价物（百万元）      680.2       1,105.6     1,532.4
资产负债率                  78.5%       65.3%       52.1%

市场环境

恒生指数近一个月下跌约4.2%，港股生物科技板块日均成交额较上月萎缩约18%。
近期港股IPO首日破发率约45%，认购倍数中位数约2.3倍。
```

---

## 三、完整输出说明

运行后，终端会输出如下格式的完整报告：

```
================================================================================
完整风险报告输出
================================================================================

报告ID:     xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
招股书ID:   example_bxk_02315
公司名称:   百奥赛图基因科技有限公司
生成时间:   2026-07-01T10:30:00

--- 综合风险评估 ---
综合风险评分:   72.35/100
综合风险等级:   high
基本面风险评分: 78.20/100 (权重0.65)
市场情绪评分:   61.47/100 (权重0.35)

--- 风险因子明细 ---
  [HIGH] 法律风险
    评分: 75.0 | 权重: 0.3 | 贡献度: 22.5
    来源: legal | 描述: 发现3个高危法律风险
  [HIGH] 财务操纵风险
    评分: 60.0 | 权重: 0.25 | 贡献度: 15.0
    来源: finance | 描述: 发现2个高危财务操纵信号
  [HIGH] 现金流消耗风险
    评分: 80.0 | 权重: 0.2 | 贡献度: 16.0
    来源: finance | 描述: 中性假设下资金耗尽时间仅15.7个月
  [HIGH] 极端市场行情
    评分: 90.0 | 权重: 0.15 | 贡献度: 13.5
    来源: sentiment | 描述: 市场出现极端行情，评分可靠度降级
  [MEDIUM] 大盘低迷
    评分: 62.0 | 权重: 0.1 | 贡献度: 6.2
    来源: sentiment | 描述: 大盘冷暖评分仅38，市场环境偏冷

--- 冲突记录 ---
检测到冲突: 1 个
  冲突类型: divergence | 描述: 法务Agent认为VIE架构风险严重，而财务分析未充分反映...

--- 辩论结果 ---
辩论轮次: 1 轮
  冲突ID: xxxxxxxxxx...
  最终解决: 是 | 不可调和: 否
  总轮次: 1 | 最终结论: 各方同意VIE架构风险应在基本面评分中给予更高权重

--- 报告摘要 ---
  综合风险评分: 72.35，风险等级: high，冲突数: 1，辩论轮次: 1

完整报告已保存至: output_example.json
================================================================================
```

### 输出字段含义

| 字段 | 含义 |
|------|------|
| `overall_score` | 综合风险评分（0-100），越高风险越大 |
| `overall_level` | 风险等级：very_low/low/medium/high/very_high |
| `fundamental_score` | 基本面风险评分（法务+财务加权） |
| `sentiment_score` | 市场情绪风险评分（反向：情绪越差分越高） |
| `factor_details` | 各风险因子明细，含评分、权重、贡献度、来源Agent |
| `conflicts` | Agent间冲突记录，含冲突类型和描述 |
| `debate_results` | 辩论过程记录，含每轮发言、立场、最终结论 |
| `summary` | 报告摘要 |

---

## 四、通过 API 调用

### 启动服务

```bash
python scripts/run.py
```

### 提交分析（纯文本）

```bash
curl -X POST http://localhost:8080/api/v1/analysis/submit \
  -H "Content-Type: application/json" \
  -d '{
    "doc_id": "my_doc_001",
    "options": {
      "text": "这里是招股书文本内容...",
      "industry": "生物科技",
      "stock_code": "02315",
      "company_name": "百奥赛图基因科技有限公司",
      "market_data": {
        "index_change": -0.042,
        "daily_change": -0.012,
        "ipo_subscription_ratio": 1.8
      }
    }
  }'
```

### 查询状态

```bash
curl http://localhost:8080/api/v1/analysis/{task_id}/status
```

### 获取报告

```bash
curl http://localhost:8080/api/v1/analysis/{task_id}/report
```

### 获取推理链路

```bash
curl http://localhost:8080/api/v1/analysis/{task_id}/trace
```

---

## 五、常见 OpenAI 兼容端点配置

| 服务商 | api_base | chat_model | 备注 |
|--------|----------|------------|------|
| OpenAI 官方 | `https://api.openai.com/v1` | gpt-4o | 需要海外网络 |
| Azure OpenAI | `https://{resource}.openai.azure.com/...` | 部署名 | 企业级 |
| DeepSeek | `https://api.deepseek.com/v1` | deepseek-chat | 国产，性价比高 |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | glm-4-plus | 国产 |
| 月之暗面 | `https://api.moonshot.cn/v1` | moonshot-v1-8k | 国产 |
| 国内代理 | `https://api.aigc361.com/v1` | gpt-4o | 中转服务 |

---

## 六、自定义分析参数

在调用 `run_full_analysis` 时可传入以下参数：

```python
report = await orchestrator.run_full_analysis(
    doc_id="my_doc_001",
    file_path="/path/to/prospectus.pdf",    # PDF路径（可选）
    company_name="公司名",
    stock_code="02315",
    industry="生物科技",
)
```

在 YAML 中可调节的全局参数：

```yaml
debate:
  max_rounds: 3              # 辩论最大轮次

fusion:
  fundamental_weight: 0.65   # 基本面权重
  sentiment_weight: 0.35     # 市场情绪权重

retrieval:
  chunk_size: 512            # 文档分片大小
  top_k: 10                  # 检索返回数量

sentiment:
  data_freshness_hours: 24   # 数据过期阈值
  extreme_move_threshold: 0.05  # 极端行情阈值
```

---

## 七、故障排查

| 问题 | 解决方案 |
|------|---------|
| `LLM调用失败` | 检查 api_key、api_base 是否正确；确认网络可达 |
| `Embedding调用失败` | 确认 embedding_model 名称正确；OpenAI 用 text-embedding-3-large |
| `Database not initialized` | 系统会降级运行，不影响核心分析；如需持久化，启动 PostgreSQL |
| `Redis连接失败` | 系统会降级运行，缓存功能不可用；如需缓存，启动 Redis |
| `结构化输出解析失败` | 系统会尝试 JSON 提取兜底；降低 temperature 可改善 |