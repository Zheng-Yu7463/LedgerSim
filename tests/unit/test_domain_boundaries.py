from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any

import pytest

from ledger_sim.domain.accounting import (
    AccountingContractError,
    AccountingCoordinator,
    JournalLine,
)
from ledger_sim.domain.commands import CommandCodecError, parse_command
from ledger_sim.domain.engine import EngineContractError
from ledger_sim.domain.sales import SalesContractError
from ledger_sim.domain.values import (
    BusinessCalendar,
    BusinessDate,
    DomainId,
    Instant,
    NonNegativeMoney,
    PositiveMoney,
    ValueContractError,
)
from tests.golden.runner import GoldenMismatch, GoldenScenarioRunner


@pytest.mark.parametrize(
    "mutation",
    ["version", "envelope_extra", "payload_extra"],
)
def test_command_codec_rejects_unversioned_or_open_shapes(
    golden_fixture: dict[str, Any],
    mutation: str,
) -> None:
    raw = copy.deepcopy(golden_fixture["steps"][0]["command"])
    if mutation == "version":
        raw["schema_version"] = "999.0.0"
    elif mutation == "envelope_extra":
        raw["unexpected"] = "forbidden"
    else:
        raw["payload"]["unexpected"] = "forbidden"

    with pytest.raises(CommandCodecError):
        parse_command(raw)


@pytest.mark.parametrize("raw", [None, [], "command"])
def test_command_codec_rejects_non_object_commands(raw: object) -> None:
    with pytest.raises(CommandCodecError, match="must be an object"):
        parse_command(raw)


@pytest.mark.parametrize(
    ("step_id", "field", "value"),
    [
        ("common-001", "fixed_consideration", "6000"),
        ("common-001", "quantity", "1"),
        ("common-001", "expires_at", "2027-01-01T00:00:00Z"),
        ("fraud-001", "target_amount", "6000.000"),
        ("fraud-001", "target_period", "2026-13"),
        ("fraud-001", "target_period", "2026-1"),
    ],
)
def test_command_codec_rejects_noncanonical_or_invalid_values(
    golden_fixture: dict[str, Any],
    step_id: str,
    field: str,
    value: str,
) -> None:
    raw = copy.deepcopy(
        next(item for item in golden_fixture["steps"] if item["step_id"] == step_id)[
            "command"
        ]
    )
    raw["payload"][field] = value

    with pytest.raises(CommandCodecError):
        parse_command(raw)


def test_command_codec_rejects_negative_payment(
    golden_fixture: dict[str, Any],
) -> None:
    raw = copy.deepcopy(
        next(item for item in golden_fixture["steps"] if item["step_id"] == "common-006")[
            "command"
        ]
    )
    raw["payload"]["amount"] = "-1.00"

    with pytest.raises(CommandCodecError, match="amount is invalid"):
        parse_command(raw)


@pytest.mark.parametrize("amount", ["0.00", "-1.00"])
def test_business_money_must_be_positive(amount: str) -> None:
    with pytest.raises(ValueContractError, match="positive"):
        PositiveMoney.parse(amount)


def test_journal_line_requires_nonnegative_exactly_one_sided_amounts() -> None:
    with pytest.raises(ValueContractError, match="negative"):
        NonNegativeMoney.parse("-1.00")
    with pytest.raises(AccountingContractError, match="exactly one positive side"):
        JournalLine(
            DomainId("line-zero"),
            "bank",
            NonNegativeMoney.zero(),
            NonNegativeMoney.zero(),
        )
    with pytest.raises(AccountingContractError, match="exactly one positive side"):
        JournalLine(
            DomainId("line-two-sided"),
            "bank",
            NonNegativeMoney.parse("1.00"),
            NonNegativeMoney.parse("1.00"),
        )


def test_business_calendar_uses_shanghai_date_boundary() -> None:
    calendar = BusinessCalendar()
    assert str(calendar.date_of(Instant.parse("2026-03-01T15:59:59.000000Z"))) == "2026-03-01"
    assert str(calendar.date_of(Instant.parse("2026-03-01T16:00:00.000000Z"))) == "2026-03-02"


def test_reported_accounting_date_is_derived_from_shipment(
    golden_fixture: dict[str, Any],
) -> None:
    run = GoldenScenarioRunner(golden_fixture).run()
    events = [event for result in run.steps.values() for event in result.events]
    order = next(
        event
        for event in events
        if event.event_type == "SalesOrderCreated" and str(event.branch_id) == "fraud-001"
    )
    shipment = next(
        event
        for event in events
        if event.event_type == "ShipmentRecordAccepted" and str(event.branch_id) == "fraud-001"
    )
    invoice = next(
        event
        for event in events
        if event.event_type == "SalesInvoiceIssued" and str(event.branch_id) == "fraud-001"
    )
    changed_invoice = replace(
        invoice,
        payload=replace(
            invoice.payload,
            invoice_date=BusinessDate.parse("2027-01-15"),
        ),
    )
    all_events = {event.event_id: event for event in events}
    all_events[changed_invoice.event_id] = changed_invoice
    coordinator = AccountingCoordinator()
    coordinator.observe(order, all_events)
    coordinator.observe(shipment, all_events)
    _, journals = coordinator.observe(changed_invoice, all_events)

    assert {str(journal.accounting_date) for journal in journals} == {"2026-12-29"}


def test_invoice_and_shipment_must_share_shanghai_business_date(
    golden_fixture: dict[str, Any],
) -> None:
    candidate = copy.deepcopy(golden_fixture)
    invoice = next(item for item in candidate["steps"] if item["step_id"] == "common-005")
    invoice["command"]["payload"]["invoice_date"] = "2027-01-15"

    with pytest.raises(SalesContractError, match="same Shanghai business date"):
        GoldenScenarioRunner(candidate).run()


def test_engine_and_runner_reject_ancestor_writes_after_fork(
    golden_fixture: dict[str, Any],
) -> None:
    run = GoldenScenarioRunner(golden_fixture).run()
    raw = copy.deepcopy(
        next(item for item in golden_fixture["steps"] if item["step_id"] == "baseline-001")[
            "command"
        ]
    )
    raw["command_id"] = "ancestor-write-after-fork"
    raw["branch_id"] = "ancestor-001"
    with pytest.raises(EngineContractError, match="sealed"):
        run.engine.handle(parse_command(raw))

    candidate = copy.deepcopy(golden_fixture)
    candidate["steps"].insert(
        7,
        {
            "step_id": "ancestor-after-fork",
            "branch_id": "ancestor-001",
            "command": raw,
            "expected_events": [],
            "expected_state_ref": "state-common-007",
        },
    )
    with pytest.raises(GoldenMismatch, match="ancestor command appears after fork"):
        GoldenScenarioRunner(candidate).run()


@pytest.mark.parametrize(
    ("path", "value", "error_type", "message"),
    [
        (("aggregate_id",), "wrong-case-aggregate", AccountingContractError, "aggregate"),
        (("business_chain_id",), "wrong-chain", AccountingContractError, "business chain"),
        (
            ("payload", "original_journal_id"),
            "wrong-original-journal",
            AccountingContractError,
            "wrong original journal",
        ),
        (("expected_version",), 1, EngineContractError, "expected version"),
    ],
)
def test_reversal_command_validates_case_identity_and_version(
    golden_fixture: dict[str, Any],
    path: tuple[str, ...],
    value: object,
    error_type: type[Exception],
    message: str,
) -> None:
    run = GoldenScenarioRunner(golden_fixture).run()
    raw = copy.deepcopy(
        next(
            item
            for item in golden_fixture["determinism_tests"]["case_lifecycle"]
            if item["action"] == "reverse"
        )["command"]
    )
    target = raw
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(error_type, match=message):
        run.engine.handle(parse_command(raw))


def test_reversal_command_rejects_inherited_ancestor_case(
    golden_fixture: dict[str, Any],
) -> None:
    run = GoldenScenarioRunner(golden_fixture).run()
    branch = DomainId("fraud-001")
    case = next(
        item
        for item in run.engine.accounting_of(branch).registry.cases
        if str(item.key.branch_id) == "ancestor-001" and item.status.value == "posted"
    )
    assert case.posted_journal_id is not None
    raw = copy.deepcopy(
        next(
            item
            for item in golden_fixture["determinism_tests"]["case_lifecycle"]
            if item["action"] == "reverse"
        )["command"]
    )
    raw["command_id"] = "reject-inherited-ancestor-reversal"
    raw["branch_id"] = str(branch)
    raw["aggregate_id"] = str(case.key.case_id)
    raw["expected_version"] = 0
    raw["business_chain_id"] = str(case.key.business_chain_id)
    raw["payload"]["accounting_case_key"] = str(case.key)
    raw["payload"]["original_journal_id"] = str(case.posted_journal_id)

    with pytest.raises(AccountingContractError, match="branch differs"):
        run.engine.handle(parse_command(raw))
