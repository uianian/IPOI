from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from src.config import IPOI_ROOT, load_yaml
from src.models.market import (
    IndicatorEvidence,
    MarketDataBoundary,
    MarketScorePack,
    MarketSentimentAnalysis,
    MarketSnapshot,
    ModuleSignalBalance,
    PublicOpinionAssessment,
)


DEFAULT_CATALOG = IPOI_ROOT / "market" / "configs" / "indicator_catalog.yaml"
MODULE_LABELS = {
    "macro": "宏观市场",
    "industry": "行业情绪",
    "ipo_market": "IPO市场",
    "public_opinion": "公司舆情",
}
STATE_LABELS = {
    "supportive": "支持因素占优",
    "neutral": "整体中性",
    "mixed": "多空信号交织",
    "pressured": "压制因素占优",
    "insufficient_data": "数据不足",
    "unavailable": "不可用",
}


def _repo_relative(path: Path | str) -> str:
    candidate = Path(path)
    try:
        return candidate.resolve().relative_to(IPOI_ROOT.resolve()).as_posix()
    except (OSError, ValueError):
        return str(candidate)


def _display_value(value: Any, display: str) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if display in {"percent", "percentage_point"}:
        suffix = "%" if display == "percent" else "个百分点"
        return f"{number * 100:.2f}{suffix}"
    if display == "integer":
        return f"{number:.0f}"
    if display == "multiple":
        return f"{number:.2f}倍"
    if display == "amount":
        return f"{number:,.4f}"
    return f"{number:.4f}"


def _escape(value: Any) -> str:
    return str(value if value is not None else "—").replace("|", "\\|").replace("\n", " ")


class MarketEvidenceBuilder:
    """Turn local market fields into an auditable evidence ledger and report."""

    def __init__(self, catalog_path: Path | str = DEFAULT_CATALOG) -> None:
        catalog = load_yaml(catalog_path)
        indicators = catalog.get("indicators") or {}
        if not isinstance(indicators, dict) or not indicators:
            raise ValueError(f"market indicator catalog is empty: {catalog_path}")
        self.catalog_path = Path(catalog_path)
        self.indicators: dict[str, dict[str, Any]] = indicators
        self.aggregation: dict[str, Any] = catalog.get("aggregation") or {}

    def build(
        self,
        snapshot: MarketSnapshot,
        score_pack: MarketScorePack,
        opinion: PublicOpinionAssessment,
        *,
        features_file: Path | str,
        news_status: dict[str, Any],
    ) -> MarketSentimentAnalysis:
        ledger: list[IndicatorEvidence] = []
        for indicator, spec in self.indicators.items():
            module = str(spec.get("module") or "macro")
            if module not in MODULE_LABELS:
                continue
            raw = snapshot.features.get(indicator)
            direction = self._direction(raw, spec)
            interpretation = self._interpretation(spec, direction, raw)
            flags: list[str] = []
            if raw is None:
                flags.append("missing_value")
            if not snapshot.cutoff_verified:
                flags.append("cutoff_unverified")
            if spec.get("quality_note"):
                flags.append(str(spec["quality_note"]))
            fallback = self._fallback_used(indicator, snapshot)
            if fallback:
                flags.append("fallback_source_used")
            provider = str(spec.get("provider") or "")
            if indicator.startswith(("ind_ret_", "ind_excess_")) and snapshot.industry_return_source:
                provider = f"{provider}；本行实际={snapshot.industry_return_source}"
            ledger.append(
                IndicatorEvidence(
                    evidence_id=str(spec.get("evidence_id") or indicator.upper()),
                    module=module,
                    indicator=indicator,
                    label=str(spec.get("label") or indicator),
                    claim=interpretation,
                    direction=direction,
                    derived_file=_repo_relative(features_file),
                    derived_field=indicator,
                    raw_value=raw,
                    display_value=_display_value(raw, str(spec.get("display") or "decimal")),
                    unit=str(spec.get("unit") or "unknown"),
                    window=str(spec.get("window") or ""),
                    formula=str(spec.get("formula") or ""),
                    upstream_files=[str(v) for v in spec.get("upstream_files") or []],
                    upstream_fields=[str(v) for v in spec.get("upstream_fields") or []],
                    provider=provider,
                    as_of_date=snapshot.as_of_date,
                    observation_date=(
                        snapshot.market_observation_date
                        if module in {"macro", "industry"}
                        else snapshot.as_of_date
                    ),
                    interpretation=interpretation,
                    quality_flags=flags,
                    fallback_used=fallback,
                )
            )

        ledger.extend(self._opinion_evidence(snapshot, opinion, news_status))
        boundary = MarketDataBoundary(
            listing_date=snapshot.listing_date,
            as_of_date=snapshot.as_of_date,
            market_observation_date=snapshot.market_observation_date,
            cutoff_verified=snapshot.cutoff_verified,
            features_file=_repo_relative(features_file),
            indicator_catalog_file=_repo_relative(self.catalog_path),
            news_file=_repo_relative(news_status["file"]) if news_status.get("file") else None,
            news_file_exists=bool(news_status.get("exists")),
            news_total_rows=int(news_status.get("total_rows") or 0),
            news_pre_cutoff_rows=int(news_status.get("pre_cutoff_rows") or 0),
            news_earliest_date=news_status.get("earliest_date"),
            news_latest_date=news_status.get("latest_date"),
            quality_flags=list(snapshot.quality_flags),
        )

        module_balances, overall_net_support, overall_state, aggregation_policy = (
            self._aggregate_signals(ledger, opinion.available)
        )
        module_states = {
            module: balance.state for module, balance in module_balances.items()
        }
        grouped = self._group(ledger)
        module_summaries = {
            module: self._module_summary(module, module_states.get(module, "unavailable"), items)
            for module, items in grouped.items()
        }
        module_coverage = {
            module: (
                sum(e.direction != "unavailable" for e in items) / len(items)
                if items
                else 0.0
            )
            for module, items in grouped.items()
        }
        support_ids = [e.evidence_id for e in ledger if e.direction == "support"]
        pressure_ids = [e.evidence_id for e in ledger if e.direction == "pressure"]
        neutral_ids = [e.evidence_id for e in ledger if e.direction == "neutral"]
        unavailable_ids = [e.evidence_id for e in ledger if e.direction == "unavailable"]
        contradictions = self._contradictions(grouped)
        limitations = self._limitations(snapshot, opinion, news_status, ledger)
        analysis = MarketSentimentAnalysis(
            overall_state=overall_state,
            overall_summary=self._overall_summary(overall_state, ledger, opinion),
            overall_net_support=round(overall_net_support, 4),
            aggregation_policy=aggregation_policy,
            module_states=module_states,
            module_signal_balances=module_balances,
            module_coverage={k: round(v, 4) for k, v in module_coverage.items()},
            module_summaries=module_summaries,
            support_evidence_ids=support_ids,
            pressure_evidence_ids=pressure_ids,
            neutral_evidence_ids=neutral_ids,
            unavailable_evidence_ids=unavailable_ids,
            contradictions=contradictions,
            limitations=limitations,
            data_boundary=boundary,
            evidence_ledger=ledger,
        )
        analysis.report_markdown = self.render_markdown(snapshot, score_pack, analysis)
        return analysis

    @staticmethod
    def _direction(raw: Any, spec: dict[str, Any]) -> str:
        if raw is None:
            return "unavailable"
        rule = str(spec.get("direction_rule") or "contextual")
        if rule == "contextual":
            return "neutral"
        try:
            number = float(raw)
        except (TypeError, ValueError):
            return "neutral"
        if rule == "positive_support":
            return "support" if number > 0 else "pressure" if number < 0 else "neutral"
        if rule == "negative_support":
            return "support" if number < 0 else "pressure" if number > 0 else "neutral"
        if rule == "above_one_support":
            return "support" if number > 1 else "pressure" if number < 1 else "neutral"
        return "neutral"

    @staticmethod
    def _interpretation(spec: dict[str, Any], direction: str, raw: Any) -> str:
        if raw is None:
            return "该指标在本地快照中缺失，本轮不据此作方向判断"
        if direction == "support":
            return str(spec.get("positive_meaning") or spec.get("context_meaning") or "形成支持信号")
        if direction == "pressure":
            return str(spec.get("negative_meaning") or spec.get("context_meaning") or "形成压制信号")
        return str(spec.get("context_meaning") or "该指标作为背景信息记录，当前不单独判定方向")

    @staticmethod
    def _fallback_used(indicator: str, snapshot: MarketSnapshot) -> bool:
        if indicator.startswith(("ind_ret_", "ind_excess_")):
            return snapshot.industry_return_source not in {None, "hsics"}
        if indicator == "hsi_vol_20d":
            return snapshot.features.get("vhsi_avg_5d") is None
        if indicator == "subscription_multiple" and snapshot.subscription_source:
            return "wind" in snapshot.subscription_source.lower()
        return False

    @staticmethod
    def _opinion_evidence(
        snapshot: MarketSnapshot,
        opinion: PublicOpinionAssessment,
        news_status: dict[str, Any],
    ) -> list[IndicatorEvidence]:
        derived_file = _repo_relative(news_status.get("file") or "")
        if not opinion.available or not opinion.evidence:
            reason = opinion.unavailable_reason or news_status.get("unavailable_reason") or "no_reliable_opinion"
            total = int(news_status.get("total_rows") or 0)
            valid = int(news_status.get("pre_cutoff_rows") or 0)
            firecrawl = news_status.get("firecrawl") or {}
            raw_cache_value = firecrawl.get("raw_cache_file")
            raw_cache = _repo_relative(raw_cache_value) if raw_cache_value else ""
            diagnostic = (
                f"Firecrawl搜索{int(firecrawl.get('search_requests') or 0)}次，"
                f"命中{int(firecrawl.get('search_hits') or 0)}条，"
                f"正文成功{int(firecrawl.get('scraped_urls') or firecrawl.get('raw_successful_articles') or 0)}条，"
                f"纳入{int(firecrawl.get('accepted_articles') or 0)}条；"
                f"超期{int(firecrawl.get('rejected_after_cutoff') or 0)}条，"
                f"缺日期{int(firecrawl.get('rejected_missing_date') or 0)}条"
            )
            upstream_files = [path for path in (derived_file, raw_cache) if path]
            flags = [reason]
            if raw_cache:
                flags.append("raw_firecrawl_cache_available")
            return [
                IndicatorEvidence(
                    evidence_id="OPINION-STATUS",
                    module="public_opinion",
                    indicator="public_opinion_availability",
                    label="上市前有效舆情可用性",
                    claim=(
                        f"本地新闻共{total}条，其中截止日前{valid}条；"
                        f"{diagnostic}；舆情未纳入，原因={reason}"
                    ),
                    direction="unavailable",
                    derived_file=derived_file,
                    derived_field="发布时间/新闻标题/新闻内容",
                    raw_value={
                        "total_rows": total,
                        "pre_cutoff_rows": valid,
                        "firecrawl": firecrawl,
                    },
                    display_value=f"{valid}/{total}条可用",
                    unit="article",
                    window=f"不晚于{snapshot.as_of_date.isoformat()}",
                    formula="发布时间校验 + LLM相关性验证",
                    upstream_files=upstream_files,
                    upstream_fields=["发布时间", "新闻标题", "新闻内容", "文章来源", "新闻链接"],
                    provider="本地新闻CSV",
                    as_of_date=snapshot.as_of_date,
                    observation_date=news_status.get("earliest_date"),
                    interpretation=(
                        f"舆情模块不可用，不参与模块权重；{reason}。{diagnostic}。"
                        + (f"原始正文已保存至{raw_cache}" if raw_cache else "")
                    ),
                    quality_flags=flags,
                )
            ]
        out: list[IndicatorEvidence] = []
        for index, evidence in enumerate(opinion.evidence, 1):
            direction_text = str(evidence.value or "neutral")
            direction = "support" if direction_text == "positive" else "pressure" if direction_text == "negative" else "neutral"
            out.append(
                IndicatorEvidence(
                    evidence_id=f"OPINION-{index:03d}",
                    module="public_opinion",
                    indicator="public_opinion_article",
                    label="上市前公司相关舆情",
                    claim=evidence.note,
                    direction=direction,
                    derived_file=derived_file,
                    derived_field="新闻标题/新闻内容",
                    raw_value=direction_text,
                    display_value=direction_text,
                    unit="article",
                    window=f"不晚于{snapshot.as_of_date.isoformat()}",
                    formula="LLM相关性与方向分类；URL/标题必须匹配本地候选",
                    upstream_files=[derived_file],
                    upstream_fields=["发布时间", "新闻标题", "新闻内容", "文章来源", "新闻链接"],
                    provider=evidence.source,
                    as_of_date=snapshot.as_of_date,
                    observation_date=evidence.observation_date,
                    interpretation=evidence.note,
                    url=evidence.url,
                    excerpt=evidence.note,
                )
            )
        return out

    @staticmethod
    def _group(ledger: list[IndicatorEvidence]) -> dict[str, list[IndicatorEvidence]]:
        grouped: dict[str, list[IndicatorEvidence]] = defaultdict(list)
        for evidence in ledger:
            grouped[evidence.module].append(evidence)
        for module in MODULE_LABELS:
            grouped.setdefault(module, [])
        return dict(grouped)

    def _aggregate_signals(
        self,
        ledger: list[IndicatorEvidence],
        opinion_available: bool,
    ) -> tuple[dict[str, ModuleSignalBalance], float, str, dict[str, Any]]:
        """Aggregate qualitative evidence without converting it to a 0-100 score."""
        grouped = self._group(ledger)
        margin = float(self.aggregation.get("qualitative_margin") or 0.10)
        methods = self.aggregation.get("module_methods") or {}
        macro_weights = {
            str(key): float(value)
            for key, value in (self.aggregation.get("macro_indicator_weights") or {}).items()
        }
        balances: dict[str, ModuleSignalBalance] = {}
        for module in MODULE_LABELS:
            available = [e for e in grouped[module] if e.direction != "unavailable"]
            directional = [e for e in available if e.direction in {"support", "pressure"}]
            method = str(methods.get(module) or "equal_directional_evidence")
            support_weight = 0.0
            pressure_weight = 0.0
            neutral_weight = 0.0
            if module == "macro":
                vhsi_available = any(
                    e.indicator == "vhsi_avg_5d" and e.raw_value is not None
                    for e in available
                )
                for evidence in available:
                    weight = macro_weights.get(evidence.indicator, 0.0)
                    if evidence.indicator == "hsi_vol_20d" and vhsi_available:
                        weight = 0.0
                    if evidence.direction == "support":
                        support_weight += weight
                    elif evidence.direction == "pressure":
                        pressure_weight += weight
                    else:
                        neutral_weight += weight
            elif directional:
                unit_weight = 1.0 / len(directional)
                support_weight = unit_weight * sum(e.direction == "support" for e in directional)
                pressure_weight = unit_weight * sum(e.direction == "pressure" for e in directional)
                neutral_weight = (
                    sum(e.direction == "neutral" for e in available) / len(available)
                    if available
                    else 0.0
                )
            elif available:
                neutral_weight = 1.0

            directional_weight = support_weight + pressure_weight
            if not available:
                state = "unavailable"
                net_support = 0.0
            elif directional_weight <= 0:
                state = "neutral"
                net_support = 0.0
            else:
                net_support = (support_weight - pressure_weight) / directional_weight
                state = (
                    "supportive"
                    if net_support > margin
                    else "pressured"
                    if net_support < -margin
                    else "mixed"
                )
            balances[module] = ModuleSignalBalance(
                module=module,
                method=method,
                support_weight=round(support_weight, 6),
                pressure_weight=round(pressure_weight, 6),
                neutral_or_context_weight=round(neutral_weight, 6),
                directional_weight=round(directional_weight, 6),
                net_support=round(net_support, 6),
                qualitative_margin=margin,
                state=state,
            )

        configured_key = (
            "overall_module_weights_with_opinion"
            if opinion_available
            else "overall_module_weights_without_opinion"
        )
        configured_weights = {
            str(key): float(value)
            for key, value in (self.aggregation.get(configured_key) or {}).items()
        }
        usable_weights = {
            module: weight
            for module, weight in configured_weights.items()
            if weight > 0 and balances.get(module) and balances[module].state != "unavailable"
        }
        total_weight = sum(usable_weights.values())
        effective_weights = {
            module: (usable_weights.get(module, 0.0) / total_weight if total_weight else 0.0)
            for module in MODULE_LABELS
        }
        overall_net_support = sum(
            balances[module].net_support * effective_weights[module]
            for module in MODULE_LABELS
        )
        has_directional = any(
            balances[module].directional_weight > 0 and effective_weights[module] > 0
            for module in MODULE_LABELS
        )
        if not total_weight:
            overall_state = "insufficient_data"
        elif not has_directional:
            overall_state = "neutral"
        else:
            overall_state = (
                "supportive"
                if overall_net_support > margin
                else "pressured"
                if overall_net_support < -margin
                else "mixed"
            )
        policy = {
            "qualitative_margin": margin,
            "configured_weight_policy": configured_key,
            "configured_module_weights": configured_weights,
            "effective_module_weights": {
                key: round(value, 6) for key, value in effective_weights.items()
            },
            "module_methods": methods,
            "formula": "net_support=(support-pressure)/(support+pressure); range [-1,1]",
            "not_a_0_100_score": True,
        }
        return balances, overall_net_support, overall_state, policy

    @staticmethod
    def _module_summary(module: str, state: str, evidence: list[IndicatorEvidence]) -> str:
        support = [e for e in evidence if e.direction == "support"][:2]
        pressure = [e for e in evidence if e.direction == "pressure"][:2]
        parts = [f"{MODULE_LABELS[module]}：{STATE_LABELS.get(state, state)}。"]
        if support:
            parts.append("支持：" + "；".join(f"{e.interpretation}[{e.evidence_id}]" for e in support) + "。")
        if pressure:
            parts.append("压制：" + "；".join(f"{e.interpretation}[{e.evidence_id}]" for e in pressure) + "。")
        if not support and not pressure:
            parts.append("本模块没有形成明确的方向性证据。")
        return "".join(parts)

    @staticmethod
    def _overall_summary(
        state: str,
        ledger: list[IndicatorEvidence],
        opinion: PublicOpinionAssessment,
    ) -> str:
        def diverse(direction: str) -> list[IndicatorEvidence]:
            selected: list[IndicatorEvidence] = []
            for module in MODULE_LABELS:
                match = next(
                    (e for e in ledger if e.module == module and e.direction == direction),
                    None,
                )
                if match:
                    selected.append(match)
                if len(selected) == 3:
                    break
            return selected

        support = diverse("support")
        pressure = diverse("pressure")
        parts = [f"上市前市场情绪呈现“{STATE_LABELS.get(state, state)}”。"]
        if support:
            parts.append("主要支持信号包括：" + "；".join(f"{e.interpretation}[{e.evidence_id}]" for e in support) + "。")
        if pressure:
            parts.append("主要压制信号包括：" + "；".join(f"{e.interpretation}[{e.evidence_id}]" for e in pressure) + "。")
        if not opinion.available:
            parts.append("本轮没有通过截止日与相关性双重校验的舆情，因此舆情不参与综合判断。")
        return "".join(parts)

    @staticmethod
    def _contradictions(grouped: dict[str, list[IndicatorEvidence]]) -> list[str]:
        out: list[str] = []
        for module, items in grouped.items():
            support = [e.evidence_id for e in items if e.direction == "support"]
            pressure = [e.evidence_id for e in items if e.direction == "pressure"]
            if support and pressure:
                out.append(
                    f"{MODULE_LABELS[module]}同时存在支持证据{support}与压制证据{pressure}，"
                    "结论必须保留这种分化，不能只引用单侧指标。"
                )
        return out

    @staticmethod
    def _limitations(
        snapshot: MarketSnapshot,
        opinion: PublicOpinionAssessment,
        news_status: dict[str, Any],
        ledger: list[IndicatorEvidence],
    ) -> list[str]:
        out = list(snapshot.quality_flags)
        missing = [e.evidence_id for e in ledger if e.direction == "unavailable"]
        if missing:
            out.append(f"缺失或不可用证据：{missing}")
        if not opinion.available:
            out.append(
                "舆情未纳入："
                + str(opinion.unavailable_reason or news_status.get("unavailable_reason") or "unknown")
            )
            firecrawl = news_status.get("firecrawl") or {}
            if firecrawl:
                out.append(
                    "Firecrawl诊断："
                    f"搜索{int(firecrawl.get('search_requests') or 0)}次，"
                    f"抓取正文{int(firecrawl.get('scraped_urls') or firecrawl.get('raw_successful_articles') or 0)}条，"
                    f"纳入{int(firecrawl.get('accepted_articles') or 0)}条，"
                    f"缺日期{int(firecrawl.get('rejected_missing_date') or 0)}条；"
                    f"原始缓存={firecrawl.get('raw_cache_file') or '无'}"
                )
        if any(e.unit == "source_unit" for e in ledger if e.raw_value is not None):
            out.append("部分资金字段的原始金额单位尚未在源文件中统一声明，报告保留原值而不猜测单位。")
        return list(dict.fromkeys(out))

    @staticmethod
    def render_markdown(
        snapshot: MarketSnapshot,
        score_pack: MarketScorePack,
        analysis: MarketSentimentAnalysis,
    ) -> str:
        boundary = analysis.data_boundary
        lines = [
            f"# {snapshot.company}（{snapshot.stock_code}）— 市场情绪分析报告",
            "",
            "## 市场情绪分析概览",
            "",
            f"- **整体状态：{STATE_LABELS.get(analysis.overall_state, analysis.overall_state)}**",
            f"- **综合净支持度：{analysis.overall_net_support:+.1%}**（范围−100%至+100%，不是0–100评分）",
            f"- {analysis.overall_summary}",
            "",
            "## 数据边界",
            "",
            "| 项目 | 值 |",
            "|---|---|",
            f"| 上市日期 | {boundary.listing_date} |",
            f"| 分析截止日 | {boundary.as_of_date} |",
            f"| 最近市场观察日 | {boundary.market_observation_date or '—'} |",
            f"| 截止日校验 | {'通过' if boundary.cutoff_verified else '未通过，仅可诊断'} |",
            f"| 特征文件 | `{_escape(boundary.features_file)}` |",
            f"| 指标来源目录 | `{_escape(boundary.indicator_catalog_file)}` |",
            f"| 新闻文件 | `{_escape(boundary.news_file or '—')}` |",
            f"| 新闻可用情况 | 截止日前 {boundary.news_pre_cutoff_rows}/{boundary.news_total_rows} 条 |",
            "",
            "## 分模块结论",
            "",
            "| 模块 | 状态 | 净支持度 | 数据覆盖率 | 结论 |",
            "|---|---|---:|---:|---|",
        ]
        for module in MODULE_LABELS:
            state = analysis.module_states.get(module, "unavailable")
            coverage_value = analysis.module_coverage.get(module)
            coverage = f"{coverage_value:.1%}" if coverage_value is not None else "—"
            balance = analysis.module_signal_balances.get(module)
            net_support = f"{balance.net_support:+.1%}" if balance else "—"
            lines.append(
                f"| {MODULE_LABELS[module]} | {STATE_LABELS.get(state, state)} | {net_support} | {coverage} | "
                f"{_escape(analysis.module_summaries.get(module, ''))} |"
            )
        lines += ["", "## 逐指标证据账本", ""]
        grouped = MarketEvidenceBuilder._group(analysis.evidence_ledger)
        for module in MODULE_LABELS:
            lines += [
                f"### {MODULE_LABELS[module]}",
                "",
                "| 证据ID | 指标 | 数值 | 方向 | 派生文件/字段 | 上游文件 | 窗口与公式 | 数据解释 | 质量标记 |",
                "|---|---|---:|---|---|---|---|---|---|",
            ]
            for evidence in grouped[module]:
                upstream = "<br>".join(f"`{_escape(p)}`" for p in evidence.upstream_files) or "—"
                source = f"`{_escape(evidence.derived_file)}` → `{_escape(evidence.derived_field)}`"
                window_formula = f"{_escape(evidence.window)}；`{_escape(evidence.formula)}`"
                flags = "；".join(_escape(v) for v in evidence.quality_flags) or "—"
                lines.append(
                    f"| {evidence.evidence_id} | {_escape(evidence.label)} | {_escape(evidence.display_value)} | "
                    f"{_escape(evidence.direction)} | {source} | {upstream} | {window_formula} | "
                    f"{_escape(evidence.interpretation)} | {flags} |"
                )
            lines.append("")
        if analysis.contradictions:
            lines += ["## 相互矛盾或分化的信号", ""]
            lines.extend(f"- {item}" for item in analysis.contradictions)
            lines.append("")
        lines += ["## 数据限制与缺失", ""]
        lines.extend(f"- {item}" for item in analysis.limitations)
        lines += [
            "",
            "## 权重口径声明",
            "",
            "- 有通过时间和相关性校验的舆情时，四个模块各占25%。",
            "- 无可靠舆情时，宏观、行业和IPO市场各占1/3，舆情不参与。",
            "- 宏观内部按走势30%、流动性40%、波动率20%、外部环境10%；行业、IPO市场和舆情按有效方向性证据等权。",
            "- 净支持度=(支持权重−压制权重)/(支持权重+压制权重)；绝对值不超过10%时标记为多空交织。",
            "- 当前报告以证据和市场情绪描述为主；0–100分数的最终业务含义待单独确认。",
            "",
        ]
        return "\n".join(lines)

