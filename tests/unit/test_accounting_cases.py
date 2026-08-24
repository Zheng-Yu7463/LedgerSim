from __future__ import annotations

from ledger_sim.domain.cases import (
    AccountingCaseError,
    AccountingCaseKey,
    AccountingCaseRegistry,
    AccountingCaseStatus,
)
from ledger_sim.domain.events import DomainEvent, FraudDecisionRecorded
from ledger_sim.domain.values import DomainId, Instant, PositiveMoney, deterministic_id

CASE_KEY = "run-golden-001|fraud-001|reported|reported_sales_revenue_v1|sales-chain-year-end-001|1"


def _input_event() -> DomainEvent:
    identifier = DomainId("event-1")
    return DomainEvent(
        event_id=identifier,
        run_id=DomainId("run-golden-001"),
        branch_id=DomainId("fraud-001"),
        aggregate_id=DomainId("aggregate-1"),
        sequence_in_commit=1,
        committed_at=Instant.parse("2026-12-29T01:00:00.000000Z"),
        actor_id=DomainId("actor-1"),
        causation_id=DomainId("command-1"),
        correlation_id=DomainId("correlation-1"),
        payload=FraudDecisionRecorded(PositiveMoney.parse("1.00"), "2026-12"),
    )


def test_accounting_case_rejects_premature_and_duplicate_lifecycle_actions() -> None:
    registry = AccountingCaseRegistry()
    case, created = registry.open(AccountingCaseKey.parse(CASE_KEY), ("source",))
    assert created
    journal_id = deterministic_id("journal", case.key, "recognition")

    try:
        case.post(journal_id)
    except AccountingCaseError as error:
        assert "before all required roles" in str(error)
    else:
        raise AssertionError("premature post was accepted")

    assert case.observe("source", _input_event())
    assert case.post(journal_id)
    assert not case.post(journal_id)

    try:
        case.post(DomainId("different-journal"))
    except AccountingCaseError as error:
        assert "already posted" in str(error)
    else:
        raise AssertionError("duplicate post with another journal was accepted")

    reversal_id = deterministic_id("journal", case.key, "reversal")
    try:
        case.reverse(journal_id, DomainId("caller-supplied-reversal"))
    except AccountingCaseError as error:
        assert "not deterministic" in str(error)
    else:
        raise AssertionError("caller-supplied reversal ID was accepted")
    assert case.reverse(journal_id, reversal_id)
    assert case.status is AccountingCaseStatus.REVERSED
    try:
        case.post(journal_id)
    except AccountingCaseError as error:
        assert "reversed" in str(error)
    else:
        raise AssertionError("reversed accounting case was posted again")
    try:
        case.reverse(journal_id, reversal_id)
    except AccountingCaseError as error:
        assert "AlreadyReversed" in str(error)
    else:
        raise AssertionError("duplicate reversal was accepted")


def test_malformed_case_key_is_rejected() -> None:
    try:
        AccountingCaseKey.parse("too|short")
    except AccountingCaseError:
        pass
    else:
        raise AssertionError("malformed accounting case key was accepted")
