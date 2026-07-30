"""TBL_BS_COMPANY: company-only BS is separate from consolidated TBL_BS."""

from __future__ import annotations

from src.retrieval.evidence_expand import (
    infer_statement_kind,
    statement_kind_compatible,
)


def test_company_bs_kind_and_compat() -> None:
    kind = infer_statement_kind(
        "非流動資產\n於附屬公司的投資\n資產淨值",
        "貴公司財務狀況表",
    )
    assert kind == "company_balance_sheet"
    assert statement_kind_compatible("company_balance_sheet", kind)
    assert not statement_kind_compatible("balance_sheet", kind)


def test_consolidated_bs_still_rejected_as_company() -> None:
    kind = infer_statement_kind(
        "非流動資產\n總資產\n資產淨值\n權益總額",
        "綜合財務狀況表",
    )
    assert kind == "balance_sheet"
    assert statement_kind_compatible("balance_sheet", kind)
    assert not statement_kind_compatible("company_balance_sheet", kind)
