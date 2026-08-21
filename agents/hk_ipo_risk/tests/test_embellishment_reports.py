from __future__ import annotations

import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from scripts.generate_analysis_report import build_master_report
from service.report_data import build_report_data
from service.report_pdf import render_report_pdf
from src.skills.embellishment_reporting import embellishment_report_data, render_embellishment_markdown
from src.skills.generate_warning_report import render_master_markdown


def _embellishment() -> dict:
    excerpts = [
        {
            "candidate_id": f"emb-{page:04d}",
            "dimension": "obscurity",
            "tactic": "risk_minimization",
            "section": "risk_factors" if page % 2 else "business",
            "page": page,
            "excerpt": f"第{page}頁經核驗的招股書原文切片",
            "context": f"第{page}頁完整上下文",
            "reason": "弱化重大风险的规模和紧迫性",
            "support_status": "contradictory",
            "score_contribution": 3 if page <= 3 else 1,
            "severity": "high",
            "confidence": "high",
            "cross_evidence": [],
        }
        for page in range(1, 13)
    ]
    return {
        "status": "complete",
        "score": 8,
        "level": "high",
        "reason": "风险因素存在多处高置信度弱化表述。",
        "coverage": {
            "first_pages": [1, 2, 3, 4, 5],
            "sections": ["summary", "risk_factors", "industry_overview", "business", "financial_information"],
            "pages_analyzed": list(range(1, 101)),
            "risk_factor_pages": list(range(20, 31)),
            "candidate_count": 20,
            "evaluated_candidate_count": 20,
            "verified_excerpt_count": 12,
        },
        "dimensions": {
            "marketing_language": {"score": 1, "finding": "1条", "evidence_ids": []},
            "ranking_manipulation": {"score": 2, "finding": "1条", "evidence_ids": []},
            "concept_packaging": {"score": 0, "finding": "0条", "evidence_ids": []},
            "obscurity": {"score": 5, "finding": "多条", "evidence_ids": []},
            "key_info_postponed": {"score": 0, "finding": "未触发", "evidence_ids": []},
        },
        "high_risk_excerpts": excerpts,
        "limitations": [],
    }


def _master() -> dict:
    return {
        "judgment": {
            "overall_score": 70,
            "risk_level_http": "HIGH",
            "level": "high",
            "confidence": "high",
            "verdict_reasoning": "综合风险较高。",
        },
        "embellishment": _embellishment(),
        "report_sections": {"composite": "综合风险较高。"},
        "risk_factors": [],
    }


def test_markdown_top10_and_http_json_all_excerpts():
    markdown = render_embellishment_markdown(_embellishment(), heading="##", top_n=10)
    assert markdown.count("經核驗的招股書原文切片") == 10
    assert "第12頁經核驗" not in markdown
    assert "风险因素页：20-30" in markdown

    report = build_report_data(
        {"master": _master(), "finance": {}, "legal": {}, "market": {}},
        overall_score=70,
        risk_level="HIGH",
    )
    assert len(report["embellishmentAnalysis"]["highRiskExcerpts"]) == 12
    assert report["embellishmentAnalysis"]["highRiskExcerpts"][0]["page"] in {1, 3}
    assert report["dimensions"][-1]["score"] == 8


def test_internal_final_markdown_and_pdf_share_embellishment_chapter():
    master = _master()
    internal = render_master_markdown(master)
    assert "文本粉飾度專項分析" in internal
    assert internal.count("經核驗的招股書原文切片") == 10

    final = build_master_report(
        {"doc_id": "analysis-test", "master": master},
        doc_name="测试公司",
        pdf_name="01234.pdf",
    )
    assert "## 四、文本粉饰度专项分析" in final
    assert final.count("經核驗的招股書原文切片") == 10
    assert "## 五、核心风险诱因与原文证据" in final

    report = build_report_data(
        {"master": master, "finance": {}, "legal": {}, "market": {}},
        overall_score=70,
        risk_level="HIGH",
    )
    pdf = render_report_pdf(report, ticker="01234")
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000


def test_legacy_first_pages_result_is_marked_partial_not_complete():
    legacy = {
        "score": 2,
        "level": "low",
        "reason": "仅依据前五页得出的旧版结论",
        "dimensions": {"obscurity": "未见晦涩表述"},
    }
    assert embellishment_report_data(legacy)["status"] == "partial"


def test_truncated_html_table_excerpt_cannot_swallow_following_markdown():
    emb = _embellishment()
    emb["high_risk_excerpts"][0]["excerpt"] = (
        "<table><tr><td>產品</td><td>階段</td></tr>"
        "<tr><td>HX009</td><td>III期</td></tr"
    )
    markdown = render_embellishment_markdown(emb, heading="##", top_n=1)
    assert "<table" not in markdown
    assert "</tr" not in markdown
    assert "> 產品 階段 HX009 III期" in markdown

    master = _master()
    master["embellishment"] = emb
    report = build_master_report(
        {"doc_id": "analysis-test", "master": master},
        doc_name="测试公司",
        pdf_name="01234.pdf",
    )
    assert "## 五、核心风险诱因与原文证据" in report
    assert "<table" not in report


def test_embellishment_factor_uses_master_attribution_and_verified_pdf_evidence():
    master = _master()
    master["risk_factors"] = [
        {
            "title": "文本粉饰度高",
            "source_agent": "finance",
            "reason": "粉饰评分10/10，文本可能掩盖关键风险。",
            "evidence": [{"page": None, "excerpt": "文本粉饰度10/10（high）"}],
        }
    ]
    report = build_master_report(
        {"doc_id": "analysis-test", "master": master},
        doc_name="测试公司",
        pdf_name="01234.pdf",
    )
    assert "该诱因来自总控决策智能体（文本粉饰度专项）" in report
    assert "原 PDF 第 1 页披露" in report
    assert "结构化结果未提供原 PDF 页码" not in report
    assert "文本粉饰度10/10（high）" not in report



def test_disabled_embellishment_is_absent_from_all_reports():
    master = _master()
    master["analysis_options"] = {"embellishment_enabled": False}
    master["embellishment"] = None

    internal = render_master_markdown(master)
    assert "文本粉飾度專項分析" not in internal

    final = build_master_report(
        {"doc_id": "analysis-disabled", "master": master},
        doc_name="测试公司",
        pdf_name="01234.pdf",
    )
    assert "文本粉饰度专项分析" not in final
    assert "## 四、核心风险诱因与原文证据" in final
    assert "## 五、四 Agent 辩论过程与收束结论" in final
    assert "## 六、当前时间窗的风险预测" in final
    assert "## 七、上市后真实行情验证" in final

    report = build_report_data(
        {"master": master, "finance": {}, "legal": {}, "market": {}},
        overall_score=70,
        risk_level="HIGH",
    )
    assert "embellishmentAnalysis" not in report
    assert "embellishment" not in {item["id"] for item in report["dimensions"]}
    pdf = render_report_pdf(report, ticker="01234")
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000
