"""
端到端示例：从纯文本输入到完整风险报告输出

使用方式：
    python scripts/run_example.py

前置条件：
    1. 已安装依赖：pip install -r requirements.txt
    2. 已配置 LLM 服务（OpenAI API 或 vLLM），见 configs/settings.yaml
    3. 如使用 OpenAI API，需设置环境变量：export OPENAI_API_KEY="sk-xxx"
"""

from __future__ import annotations

import asyncio
import json
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ============================================================
# 1. 示例招股书文本（文本格式输入）
# ============================================================

EXAMPLE_PROSPECTUS_TEXT = """
公司概况

百奥赛图基因科技有限公司（以下简称"本公司"或"发行人"）是一家专注于基因编辑及抗体药物开发的生物科技公司，
注册于开曼群岛，通过VIE架构运营中国境内实体。公司尚未实现盈利，截至最近报告期，累计亏损约人民币18.5亿元。
公司计划在香港联交所主板上市，股票代码02315，发行价区间为每股15.60-16.80港元，拟发行约1.05亿股。

风险因素

1. 未盈利风险：本公司自成立以来持续亏损。截至2024年12月31日，公司年度经营性现金净流出约人民币5.2亿元，
现金及现金等价物余额约人民币6.8亿元。按照当前消耗速度，若无法获得额外融资，公司资金预计可在未来约15个月内耗尽。
如未来研发项目未能如期推进或商业化进展不及预期，现金流消耗可能进一步加速。

2. VIE架构风险：本公司采用VIE架构运营中国境内业务，相关协议安排可能被中国监管机构认定为无效。
2023年新颁布的《境内企业境外发行证券和上市管理试行办法》对VIE架构提出了更严格的披露和备案要求，
公司目前尚未完成相关备案程序。

3. 核心管线进度风险：公司核心产品BIO-001（抗PD-1/CTLA-4双特异性抗体）目前处于II期临床试验阶段，
距离商业化仍有较长时间。同类竞品已有多款获批上市，市场竞争格局日趋激烈。

4. 关联交易风险：本公司与控股股东关联方存在大额技术服务交易，2024年度关联交易金额约人民币1.2亿元，
占公司采购总额的35%。部分关联交易定价的公允性存在疑虑，可能构成利益输送。

5. 对赌与赎回条款：公司历史上多轮融资中签署了对赌协议及赎回条款，若公司未能在2025年6月30日前完成上市，
投资者有权要求公司以年化8%的回报率赎回股份。该等条款可能对公司的现金流产生重大压力。

6. 知识产权风险：公司核心专利BIO-001的相关专利正在被第三方提起无效宣告请求，若专利被宣告无效，
将对公司的核心竞争力和商业前景产生重大不利影响。

7. 客户集中度风险：公司前五大客户贡献了约62%的营业收入，其中最大客户占比约28%。
若主要客户终止合作或大幅减少采购，将严重影响公司收入。

财务数据

项目                        2024年      2023年      2022年
营业收入（百万元）          328.5       215.3       142.7
营业成本（百万元）          186.2       135.8       98.4
毛利（百万元）              142.3       79.5        44.3
毛利率                      43.3%       36.9%       31.0%
研发费用（百万元）          285.6       238.4       195.2
研发费用占比                86.9%       110.7%      136.8%
净利润（百万元）            -512.3      -438.7      -365.2
经营性现金流净额（百万元）  -518.5      -426.3      -342.8
现金及等价物（百万元）      680.2       1,105.6     1,532.4
资产负债率                  78.5%       65.3%       52.1%

同行估值比较

公司          PE(TTM)    PB      PS       EV/EBITDA
行业均值       25.3     3.2     8.5        18.6
行业中位数     22.1     2.8     7.2        16.3
发行人(预计)   N/A     5.8    12.3        N/A

市场环境

恒生指数近一个月下跌约4.2%，港股生物科技板块日均成交额较上月萎缩约18%。
近期港股IPO首日破发率约45%，认购倍数中位数约2.3倍。
本公司的公开认购倍数约为1.8倍，国际配售部分获轻微超额认购。
市场情绪整体偏谨慎，大盘冷暖评分约38分（满分100）。
"""

# ============================================================
# 2. 市场情绪数据（模拟输入）
# ============================================================

MARKET_DATA = {
    "index_change": -0.042,
    "turnover_change": -0.18,
    "daily_change": -0.012,
    "sector_daily_turnover": 8.5e8,
    "sector_turnover_rate": 0.028,
    "ipo_subscription_ratio": 1.8,
    "news": [
        {"title": "港股生物科技板块持续承压", "sentiment": "negative"},
        {"title": "近期港股IPO首日破发率达45%", "sentiment": "negative"},
    ],
}

# ============================================================
# 3. 同行估值数据
# ============================================================

PEER_DATA = [
    {"PE": 25.3, "PB": 3.2, "PS": 8.5, "EV_EBITDA": 18.6},
    {"PE": 22.1, "PB": 2.8, "PS": 7.2, "EV_EBITDA": 16.3},
    {"PE": 28.5, "PB": 3.8, "PS": 9.1, "EV_EBITDA": 20.2},
    {"PE": 19.8, "PB": 2.5, "PS": 6.8, "EV_EBITDA": 15.1},
    {"PE": 30.2, "PB": 4.1, "PS": 10.3, "EV_EBITDA": 22.5},
]


# ============================================================
# 4. 主流程
# ============================================================

async def run_example():
    from src.config import settings
    from src.llm.client import VLLMClient
    from src.skills.registry import SkillRegistry
    from src.skills.long_doc_retrieval.skill import LongDocRetrievalSkill
    from src.skills.peer_comparison.skill import PeerComparisonSkill
    from src.skills.cash_flow.skill import CashFlowCalculationSkill
    from src.skills.sentiment_scoring.skill import SentimentScoringSkill
    from src.skills.base import SkillInput
    from src.agents.master.agent import MasterOrchestrator

    print("=" * 80)
    print("港股IPO多智能体风险预警系统 — 端到端示例")
    print("=" * 80)

    # ---- Step 1: 初始化 ----
    print("\n[Step 1] 初始化 LLM 客户端和组件...")

    vllm_client = VLLMClient()
    await vllm_client.init()

    llm_ok = await vllm_client.health_check()
    if llm_ok:
        print(f"  ✓ LLM 服务已连接 (provider={settings.llm.provider}, model={settings.llm.chat_model})")
    else:
        print(f"  ⚠ LLM 服务不可达 (base_url={settings.llm.base_url})")
        print("  提示：请检查 configs/settings.yaml 中的 LLM 配置，确保 API Key 和端点正确")
        print("  继续运行将以降级模式执行...\n")

    skill_registry = SkillRegistry()
    doc_skill = LongDocRetrievalSkill(vllm_client)
    peer_skill = PeerComparisonSkill()
    cash_skill = CashFlowCalculationSkill()
    sent_skill = SentimentScoringSkill()
    skill_registry.register_skill(doc_skill)
    skill_registry.register_skill(peer_skill)
    skill_registry.register_skill(cash_skill)
    skill_registry.register_skill(sent_skill)
    print(f"  ✓ 已注册 {len(skill_registry.list_skills())} 个 Skill")

    # ---- Step 2: 索引文档（纯文本输入）----
    print("\n[Step 2] 索引招股书文本...")
    doc_id = "example_bxk_02315"

    index_result = await doc_skill.execute(SkillInput(
        doc_id=doc_id,
        params={"action": "index_text", "text": EXAMPLE_PROSPECTUS_TEXT},
    ))
    if index_result.success:
        print(f"  ✓ 文本索引完成：{index_result.data['chunk_count']} 个分片")
    else:
        print(f"  ✗ 索引失败：{index_result.error}")
        return

    # ---- Step 3: 加载同行数据 ----
    print("\n[Step 3] 加载同行估值数据...")
    peer_load = await peer_skill.execute(SkillInput(
        doc_id=doc_id,
        params={"action": "load_data", "industry": "生物科技", "peer_data": PEER_DATA},
    ))
    print(f"  ✓ 同行数据加载完成：{peer_load.data.get('loaded_count', 0)} 家可比公司")

    # ---- Step 4: 运行完整分析 ----
    print("\n[Step 4] 运行多智能体协同分析...")
    print("  → 法务合规Agent：检索法律风险 → 抽取特征 → 严重程度分级 → 交叉验证")
    print("  → 财务穿透Agent：指标抽取 → 勾稽校验 → 现金流测算 → 操纵识别")
    print("  → 市场情绪Agent：大盘冷暖 → 板块流动性 → 舆情 → 评分")
    print("  → 冲突检测 → 辩论协议 → 跨模态融合 → 报告生成")
    print()

    from src.db.database import Database
    from src.db.repositories.trace_repo import TraceRepo
    from src.tracing.logger import TraceAuditLogger, TraceContext

    db = Database()
    try:
        await db.init()
        trace_repo = TraceRepo(db)
    except Exception:
        trace_repo = None

    trace_logger = TraceAuditLogger(trace_repo) if trace_repo else None

    orchestrator = MasterOrchestrator(vllm_client, skill_registry, trace_logger)

    if trace_logger:
        trace_logger.set_context(doc_id)
    else:
        from src.db.database import Database as _DB
        from src.db.repositories.trace_repo import TraceRepo as _TR
        _db = _DB()
        try:
            await _db.init()
            trace_logger = TraceAuditLogger(_TR(_db))
            trace_logger.set_context(doc_id)
            orchestrator._trace_logger = trace_logger
        except Exception:
            pass

    report = await orchestrator.run_full_analysis(
        doc_id=doc_id,
        company_name="百奥赛图基因科技有限公司",
        stock_code="02315",
        industry="生物科技",
    )

    # ---- Step 5: 输出完整报告 ----
    print("\n" + "=" * 80)
    print("完整风险报告输出")
    print("=" * 80)

    report_dict = report.model_dump()

    print(f"\n报告ID:     {report_dict.get('report_id', 'N/A')}")
    print(f"招股书ID:   {report_dict.get('doc_id', 'N/A')}")
    print(f"公司名称:   {report_dict.get('company_name', 'N/A')}")
    print(f"生成时间:   {report_dict.get('generated_at', 'N/A')}")

    assessment = report_dict.get("risk_assessment")
    if assessment:
        print(f"\n--- 综合风险评估 ---")
        print(f"综合风险评分:   {assessment.get('overall_score', 'N/A')}/100")
        print(f"综合风险等级:   {assessment.get('overall_level', 'N/A')}")
        print(f"基本面风险评分: {assessment.get('fundamental_score', 'N/A')}/100 (权重{assessment.get('fundamental_weight', 'N/A')})")
        print(f"市场情绪评分:   {assessment.get('sentiment_score', 'N/A')}/100 (权重{assessment.get('sentiment_weight', 'N/A')})")

        print(f"\n--- 风险因子明细 ---")
        for f in assessment.get("factor_details", []):
            print(f"  [{f.get('risk_level', '?').upper()}] {f.get('factor_name', 'N/A')}")
            print(f"    评分: {f.get('score', 'N/A')} | 权重: {f.get('weight', 'N/A')} | 贡献度: {f.get('contribution', 'N/A')}")
            print(f"    来源: {f.get('source_agent', 'N/A')} | 描述: {f.get('description', 'N/A')}")
    else:
        print("\n  (风险评估数据为空，可能 LLM 服务未正确配置)")

    conflicts = report_dict.get("conflicts", [])
    print(f"\n--- 冲突记录 ---")
    print(f"检测到冲突: {len(conflicts)} 个")
    for c in conflicts:
        print(f"  冲突类型: {c.get('conflict_type', 'N/A')} | 描述: {c.get('description', 'N/A')[:100]}")

    debates = report_dict.get("debate_results", [])
    print(f"\n--- 辩论结果 ---")
    print(f"辩论轮次: {len(debates)} 轮")
    for d in debates:
        print(f"  冲突ID: {d.get('conflict_id', 'N/A')[:16]}...")
        print(f"  最终解决: {'是' if d.get('final_resolved') else '否'} | 不可调和: {'是' if d.get('is_irreconcilable') else '否'}")
        print(f"  总轮次: {d.get('total_rounds', 0)} | 最终结论: {str(d.get('final_conclusion', 'N/A'))[:100]}")

    print(f"\n--- 报告摘要 ---")
    print(f"  {report_dict.get('summary', 'N/A')}")

    # ---- Step 6: 保存 JSON ----
    output_path = Path(__file__).resolve().parent.parent / "output_example.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report_dict, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n完整报告已保存至: {output_path}")

    # 清理
    await vllm_client.close()
    if db._engine:
        await db.close()

    print("\n" + "=" * 80)
    print("示例运行完毕")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_example())