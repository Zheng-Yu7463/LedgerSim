from __future__ import annotations

import copy
from decimal import Decimal
from typing import Any

import pytest

from ledger_sim.domain.accounting import AccountingCaseError
from ledger_sim.domain.replay import GoldenReplay, ReplayMismatch
from ledger_sim.domain.sales import SalesContractError


def test_all_steps_replay_to_frozen_four_layer_snapshots(
    golden_fixture: dict[str, Any],
) -> None:
    result = GoldenReplay(golden_fixture).run()

    baseline = result.branches["baseline-001"]
    fraud = result.branches["fraud-001"]
    assert baseline.reported.to_fixture() == baseline.normative.to_fixture()
    assert baseline.reported.to_fixture() == fraud.reported.to_fixture()
    assert fraud.reported.profit - fraud.normative.profit == Decimal("4000.00")


def test_replay_rejects_mutated_economic_snapshot(golden_fixture: dict[str, Any]) -> None:
    candidate = copy.deepcopy(golden_fixture)
    candidate["state_snapshots"]["state-common-001"]["economic"]["physical_inventory_quantity"] = (
        "999.0000"
    )

    with pytest.raises(ReplayMismatch, match="state differs"):
        GoldenReplay(candidate).run()


def test_replay_rejects_command_event_amount_divergence(
    golden_fixture: dict[str, Any],
) -> None:
    candidate = copy.deepcopy(golden_fixture)
    invoice_step = next(
        step
        for step in candidate["steps"]
        if step["command"]["command_id"] == "cmd-fraud-invoice-001"
    )
    invoice_step["command"]["payload"]["net_amount"] = "9999.00"

    with pytest.raises(SalesContractError, match="invoice"):
        GoldenReplay(candidate).run()


def test_dispatch_at_expiry_is_rejected(golden_fixture: dict[str, Any]) -> None:
    candidate = copy.deepcopy(golden_fixture)
    dispatch_step = next(step for step in candidate["steps"] if step["step_id"] == "common-003")
    expires_at = next(
        step["command"]["payload"]["expires_at"]
        for step in candidate["steps"]
        if step["step_id"] == "common-001"
    )
    dispatch_step["command"]["payload"]["dispatched_at"] = expires_at
    dispatch_event = next(
        event
        for event in dispatch_step["expected_events"]
        if event["event_type"] == "PhysicalGoodsDispatched"
    )
    dispatch_event["payload"]["dispatched_at"] = expires_at

    with pytest.raises(SalesContractError, match="not effective"):
        GoldenReplay(candidate).run()


def test_journal_amount_must_follow_source_event_arithmetic(
    golden_fixture: dict[str, Any],
) -> None:
    candidate = copy.deepcopy(golden_fixture)
    journal = next(
        item
        for item in candidate["journals"]
        if item["journal_id"] == "journal-report-fraud-revenue-001"
    )
    journal["lines"][0]["debit_amount"] = "9999.00"
    journal["lines"][1]["credit_amount"] = "9999.00"

    with pytest.raises((ReplayMismatch, AccountingCaseError)):
        GoldenReplay(candidate).run()
