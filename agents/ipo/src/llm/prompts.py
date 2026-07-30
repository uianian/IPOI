from __future__ import annotations

LEGAL_RISK_EXTRACTION = """你是一名专业的港股IPO法务合规分析师。请从以下招股书文本片段中，抽取法律风险特征。

重点关注：
- 诉讼与仲裁
- 行政处罚与监管措施
- 知识产权纠纷
- VIE架构合规性
- 对赌/赎回条款
- 关联交易合规性
- 数据合规与隐私保护
- 环保合规

请按以下JSON格式输出：
{{
    "risk_features": [
        {{
            "feature_name": "风险特征名称",
            "description": "详细描述",
            "severity": "high/medium/low",
            "legal_basis": "法律条款引用（如有）",
            "evidence_text": "原文支撑片段"
        }}
    ]
}}

招股书文本：
{text}

请严格基于原文内容抽取，不得臆造不存在的信息。如果某个风险特征在文本中没有明确的原文支撑，请将该特征的severity设为"low"并在evidence_text中标注"无直接原文支撑"。"""

LEGAL_SEVERITY_GRADING = """你是一名专业的港股IPO法务合规分析师。请对以下法律风险特征进行严重程度分级。

分级标准：
- high（高危）：必须关联至少一条具体法律条款或监管规定引用，且可能导致上市受阻或重大处罚
- medium（中危）：存在合规瑕疵，但不会直接导致上市受阻
- low（低危）：潜在风险，需要关注但当前影响有限

风险特征：
{features}

请输出JSON格式：
{{
    "graded_features": [
        {{
            "feature_name": "风险特征名称",
            "severity": "high/medium/low",
            "grading_reason": "分级理由",
            "legal_basis_required": true/false
        }}
    ]
}}"""

LEGAL_CROSS_REFERENCE = """你是一名法务交叉验证分析师。请检查以下法律风险特征与招股书其他章节内容的一致性。

风险特征：
{features}

其他章节内容：
{cross_content}

请判断是否存在矛盾或遗漏，输出JSON格式：
{{
    "cross_references": [
        {{
            "source_feature": "源风险特征",
            "target_section": "目标章节",
            "consistency": true/false,
            "note": "不一致说明（如有）"
        }}
    ],
    "needs_full_scan": true/false
}}"""

FINANCIAL_INDICATOR_EXTRACTION = """你是一名专业的港股IPO财务分析师。请从以下招股书财务文本中抽取标准化财务指标。

请抽取以下类型的指标：
- 营业收入、净利润、毛利率
- 经营性现金流净额、现金及等价物余额
- 资产负债率、流动比率
- 研发费用、研发费用占比

请按以下JSON格式输出：
{{
    "indicators": [
        {{
            "name": "指标名称",
            "value": "指标值",
            "unit": "单位",
            "period": "报告期",
            "source_page": null
        }}
    ]
}}

财务文本：
{text}"""

FINANCIAL_VALIDATION = """你是一名专业的财务审计分析师。请对以下财务指标进行勾稽关系校验。

校验内容：
1. 表内勾稽关系：如 营业收入-营业成本=毛利
2. 跨期连续性：同指标在不同期间的变化是否合理
3. 同行横向对比：与行业均值对比是否异常

财务指标：
{indicators}

同行数据：
{peer_data}

请输出JSON格式：
{{
    "validation_results": [
        {{
            "indicator_name": "校验指标",
            "check_type": "internal_consistency/cross_period/peer_comparison",
            "passed": true/false,
            "deviation": null,
            "note": "异常说明（如有）"
        }}
    ]
}}"""

FINANCIAL_MANIPULATION_DETECTION = """你是一名专业的财务操纵识别分析师。请从以下财务数据中识别潜在的财务操纵信号。

重点关注：
- 收入确认异常（如期末收入激增）
- 应收账款与收入不匹配
- 现金流与利润严重背离
- 关联交易占比异常
- 频繁会计政策变更

财务数据：
{financial_data}

请输出JSON格式：
{{
    "manipulation_signals": [
        {{
            "signal_name": "操纵信号名称",
            "description": "信号描述",
            "severity": "high/medium/low",
            "cross_evidence_count": 0
        }}
    ]
}}"""

SENTIMENT_EVENT_EXTRACTION = """你是一名专业的市场舆情分析师。请从以下市场信息中提取可能影响IPO表现的关键事件。

市场信息：
{market_data}

请输出JSON格式：
{{
    "events": [
        {{
            "event_name": "事件名称",
            "event_type": "policy/macro/sector/company",
            "impact_assessment": "影响评估",
            "sentiment_direction": "positive/negative/neutral"
        }}
    ]
}}"""

CONSISTENCY_VERIFICATION = """你是一名交叉验证分析师。请判断以下两个Agent的分析结论是否存在逻辑冲突。

Agent A（{agent_a}）结论：
{conclusion_a}

Agent B（{agent_b}）结论：
{conclusion_b}

请输出JSON格式：
{{
    "has_conflict": true/false,
    "conflict_type": "semantic/divergence/evidence_gap",
    "conflict_description": "冲突描述（如有）",
    "suggested_resolution": "建议解决方式（如有）"
}}"""

CONFLICT_DEBATE = """你是{agent_role}角色的代表。在多Agent协作尽调中，另一个Agent对你的分析结论提出了质疑。

你的原始结论：
{original_conclusion}

质疑内容：
{challenge}

补充证据：
{additional_evidence}

请根据你掌握的证据，选择以下立场之一：
- assert：坚持原结论，提供更详细的论证
- concede：承认质疑合理，修正结论
- clarify：澄清误解，说明原结论的真实含义

请输出JSON格式：
{{
    "stance": "assert/concede/clarify",
    "content": "你的回应内容",
    "evidence_supplement": "补充的证据（如有）",
    "conclusion_revised": "修正后的结论（如concede）"
}}"""