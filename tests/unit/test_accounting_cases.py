from __future__ import annotations

import pytest

from ledger_sim.domain.accounting import (
    AccountingCaseError,
    AccountingCaseKey,
    AccountingCaseStatus,
)
from ledger_sim.domain.cases import AccountingCaseRegistry

CASE_KEY = "run-golden-001|fraud-001|reported|reported_sales_revenue_v1|sales-chain-year-end-001|1"


def test_accounting_case_posts_once_reverses_once_and_reopens_idempotently() -> None:
    registry = AccountingCaseRegistry()
    case = registry.open(AccountingCaseKey.parse(CASE_KEY))
    assert registry.open(case.key) is case
    assert case.status is AccountingCaseStatus.PENDING

    assert case.observe("evt-fraud-003", "shipment_record")
    assert not case.observe("evt-fraud-003", "shipment_record")
    case.post("journal-report-fraud-revenue-001")
    case.post("journal-report-fraud-revenue-001")
    assert case.status is AccountingCaseStatus.POSTED

    case.reverse("journal-reversal-001")
    assert case.status is AccountingCaseStatus.REVERSED
    with pytest.raises(AccountingCaseError, match="AlreadyReversed"):
        case.reverse("journal-reversal-002")

    successor = registry.open_next(case)
    assert successor.key.recognition_cycle == 2
    assert successor.status is AccountingCaseStatus.PENDING
    assert registry.open_next(case) is successor


def test_malformed_case_key_is_rejected() -> None:
    with pytest.raises(AccountingCaseError):
        AccountingCaseKey.parse("too|short")
