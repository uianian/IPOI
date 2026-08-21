# 市场情绪 Agent：服务器部署与验收

先部署到独立 worktree/目录并使用备用端口验证，不要直接覆盖正在运行的财务/法务服务。

## 安装

    cd /path/to/IPOI/agents/hk_ipo_risk
    python3.10 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    pip install -r requirements-market.txt

必需的本地数据：

- market/data/derived/ipo_sentiment_features.csv
- market/configs/historical_scoring.yaml
- 上市后验证另需（不提交 Git）dataset/hkshareeodprices.csv

## 配置

    cp configs/market_agent.local.example.yaml configs/market_agent.local.yaml
    cp configs/firecrawl.local.example.yaml configs/firecrawl.local.yaml
    chmod 600 configs/*.local.yaml

推荐通过环境变量传密钥：

    export IPO_LLM_API_KEY='...'
    export FIRECRAWL_API_KEY='...'
    export MARKET_DATABASE_URL='postgresql+asyncpg://USER:PASSWORD@HOST:5432/DB'

第一次验收先在 configs/firecrawl.local.yaml 中设 enabled: false，确认零联网流程。

## 零额度离线验收

    python -m compileall -q src scripts service
    python -m unittest discover -s tests -p 'test_market*.py'
    python scripts/run_market_agent.py --stock-code 02451 --doc-id smoke-02451-offline

应看到：

- scoring_mode=historical_rules_floor（没配 LLM 时）
- prelisting_day1_break_risk_score 为 0–100
- JSON：.runtime/market/smoke-02451-offline_02451_market.json
- 报告：reports/smoke-02451-offline_market_report.md
- 辩论证据：.runtime/debate/*_market_dossier_*.json

## LLM 与 ReAct 验收

配置 LLM Key，但继续保持 Firecrawl 关闭：

    python scripts/run_market_agent.py --stock-code 02451 --doc-id smoke-02451-llm

检查 JSON 中的 features.deterministic_score、features.llm_score、
features.score_reconciliation、features.react_turns 和
features.debate_dossier_path。最终分不低于确定性历史校准底线；LLM 引用
不存在的证据 ID 时，其评分会被拒绝。

## Firecrawl（只主动消费一次）

把 configs/firecrawl.local.yaml 的 enabled 改为 true，然后仅运行一次：

    python scripts/fetch_market_news_firecrawl.py --stock-code 02451 --out .runtime/firecrawl_02451_status.json

正常上限是一次 search、五次 scrape。无论发布日期能否通过严格校验，原始
搜索及正文均写入
market/data/external/news/raw/02451_2023-10-11_firecrawl.json；只有合格
文章才进入 market/data/external/news/02451.csv。

不要在日常测试使用 --refresh-firecrawl。第二次直接运行应复用原始缓存。

## 上市后 D1/D5–D60

先在仓库根目录构建检查点：

    python market/scripts/build_postlisting_checkpoints.py

再运行：

    cd agents/hk_ipo_risk
    python scripts/run_market_postlisting.py --stock-code 02451 --doc-id smoke-02451-post --through-day 60

结果必须包含 D1 以及 D5 至 D60 每五个交易日一个检查点。below_issue_price
是主要破发锚点；累计收益以首个交易日开盘价为基准。D1 检查点用于首日
破发验证，D5 用于总控重点显著下跌预警复盘。

## 三 Agent 并行与 9102 服务

先用统一 CLI：

    python scripts/run_finance_legal.py --agent all --stock-code 02451 --doc-id REAL_TASK_ID --doc-name 綠源集團控股 --pdf-name 02451_test.pdf --use-live-retrieval --out .runtime/all_02451.json

有真实市场结果时，对照分按 `(legal×0.55 + finance×0.45)×0.65 + market×0.35` 计入 `reference_fundamental_score`。

服务先在备用端口启动：

    ANALYSIS_PORT=19102 uvicorn service.app:app --host 0.0.0.0 --port 19102
    curl -s http://127.0.0.1:19102/health

通过既有 /api/v1/projects/{clientProjectId}/analysis/start 发起真实任务后，
结果应满足：

- agents.financial、agents.legal、agents.market 均有结果；
- agents.market.marketDetail 含确定性分、LLM 分、证据目录和 dossier 路径；
- dossierPaths.market 非空；
- 市场失败只写入 market_error，不会丢失财务/法务结果。

## PostgreSQL（可选）

第一轮文件落盘验收通过后再启用。在 configs/market_agent.local.yaml 中设置
database.enabled=true、database.required=true、schema=market_agent。
应用会自动建表；也可由 DBA 先执行 migrations/001_market_evidence.sql。
