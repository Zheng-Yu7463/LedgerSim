from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any

import pytest

from ledger_sim.domain.accounting import AccountingCoordinator
from ledger_sim.domain.cases import AccountingCaseError, AccountingCaseStatus
from ledger_sim.domain.commands import parse_command
from ledger_sim.domain.events import JournalPosted
from ledger_sim.domain.idempotency import CommandIdConflict
from ledger_sim.domain.sales import SalesContractError
from ledger_sim.domain.state import EventReducer, StateContractError
from ledger_sim.domain.values import DomainId, Money, Quantity, UnitPrice, deterministic_id
from tests.golden.runner import GoldenMismatch, GoldenScenarioRunner


def test_command_driven_scenario_matches_all_frozen_outputs(
    golden_fixture: dict[str, Any],
) -> None:
    result = GoldenScenarioRunner(golden_fixture).run()

    baseline = result.engine.state_of(DomainId("baseline-001"))
    fraud = result.engine.state_of(DomainId("fraud-001"))
    assert baseline.reported == baseline.normative
    assert baseline.reported == fraud.reported
    assert fraud.reported.profit - fraud.normative.profit == Money.parse("4000.00")
    assert len(result.steps) == len(golden_fixture["steps"])
    assert sum(len(step.journals) for step in result.steps.values()) == 12


@pytest.mark.parametrize("mutation", ["extra", "missing", "sequence"])
def test_expected_events_are_outputs_only_and_mismatches_are_rejected(
    golden_fixture: dict[str, Any],
    mutation: str,
) -> None:
    candidate = copy.deepcopy(golden_fixture)
    events = candidate["steps"][0]["expected_events"]
    if mutation == "extra":
        events.append(copy.deepcopy(events[0]))
        events[-1]["event_id"] = "extra-without-cause"
        events[-1]["sequence_in_commit"] = 2
    elif mutation == "missing":
        events.clear()
    else:
        events[0]["sequence_in_commit"] = 99

    with pytest.raises(GoldenMismatch, match="events differ"):
        GoldenScenarioRunner(candidate).run()


@pytest.mark.parametrize(
    ("step_id", "path", "value", "message"),
    [
        ("common-001", ("payload", "company_id"), "wrong-company", "company"),
        ("common-004", ("payload", "customer_id"), "wrong-customer", "shipment"),
        ("common-005", ("payload", "product_id"), "wrong-product", "invoice"),
        ("common-004", ("business_chain_id",), "wrong-chain", "business chain"),
        (
            "common-002",
            ("payload", "claimed_commitment_id"),
            "missing-commitment",
            "missing commitment",
        ),
        ("common-001", ("expected_version",), 1, "expected version"),
    ],
)
def test_invalid_command_references_and_version_are_rejected(
    golden_fixture: dict[str, Any],
    step_id: str,
    path: tuple[str, ...],
    value: object,
    message: str,
) -> None:
    candidate = copy.deepcopy(golden_fixture)
    step = next(item for item in candidate["steps"] if item["step_id"] == step_id)
    target = step["command"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(SalesContractError, match=message):
        GoldenScenarioRunner(candidate).run()


def test_invoice_arithmetic_is_command_driven(golden_fixture: dict[str, Any]) -> None:
    candidate = copy.deepcopy(golden_fixture)
    step = next(item for item in candidate["steps"] if item["step_id"] == "fraud-004")
    step["command"]["payload"]["net_amount"] = "9999.00"

    with pytest.raises(SalesContractError, match="quantity times unit price"):
        GoldenScenarioRunner(candidate).run()


def test_dispatch_uses_half_open_commitment_interval(
    golden_fixture: dict[str, Any],
) -> None:
    candidate = copy.deepcopy(golden_fixture)
    commitment = next(item for item in candidate["steps"] if item["step_id"] == "common-001")
    dispatch = next(item for item in candidate["steps"] if item["step_id"] == "common-003")
    dispatch["command"]["payload"]["dispatched_at"] = commitment["command"]["payload"]["expires_at"]

    with pytest.raises(SalesContractError, match="not effective"):
        GoldenScenarioRunner(candidate).run()


def test_round_half_up_boundary() -> None:
    assert Money.parse("1.005") == Money.parse("1.01")
    assert UnitPrice.parse("0.1005").total(Quantity.parse("10")) == Money.parse("1.01")


def test_mutated_state_snapshot_is_rejected(golden_fixture: dict[str, Any]) -> None:
    candidate = copy.deepcopy(golden_fixture)
    candidate["state_snapshots"]["state-common-001"]["economic"]["physical_inventory_quantity"] = (
        "999.0000"
    )

    with pytest.raises(GoldenMismatch, match="state differs"):
        GoldenScenarioRunner(candidate).run()


def test_command_retry_vectors_run_through_domain_engine(
    golden_fixture: dict[str, Any],
) -> None:
    result = GoldenScenarioRunner(golden_fixture).run()
    commands = {step["command"]["command_id"]: step["command"] for step in golden_fixture["steps"]}
    branch = DomainId("fraud-001")
    original_event_count = len(result.engine.events_of(branch))
    original_journal_count = len(result.engine.journals_of(branch))

    for vector in golden_fixture["determinism_tests"]["command_retries"]:
        raw = copy.deepcopy(commands[vector["command_ref"]])
        mutation = vector["mutation"]
        if isinstance(mutation, dict):
            for dotted_path, value in mutation.items():
                target = raw
                parts = dotted_path.split(".")
                for part in parts[:-1]:
                    target = target[part]
                target[parts[-1]] = value
        command = parse_command(raw)

        if vector["expected_result"] == "return_original_result":
            replayed = result.engine.handle(command)
            assert replayed is result.steps["fraud-004"]
        else:
            with pytest.raises(CommandIdConflict):
                result.engine.handle(command)
        assert len(result.engine.events_of(branch)) == original_event_count
        assert len(result.engine.journals_of(branch)) == original_journal_count


def test_event_order_permutations_use_real_accounting_coordinator(
    golden_fixture: dict[str, Any],
) -> None:
    run = GoldenScenarioRunner(golden_fixture).run()
    all_events = {event.event_id: event for result in run.steps.values() for event in result.events}
    digests_by_group: dict[str, list[tuple[tuple[str, str], ...]]] = {}

    for vector in golden_fixture["determinism_tests"]["event_order_permutations"]:
        inputs = [all_events[DomainId(event_id)] for event_id in vector["event_refs"]]
        chain_id = inputs[0].business_chain_id
        order = next(
            event
            for event in all_events.values()
            if event.event_type == "SalesOrderCreated"
            and event.branch_id == inputs[0].branch_id
            and event.business_chain_id == chain_id
        )
        coordinator = AccountingCoordinator()
        coordinator.observe(order, all_events)
        journals = []
        for event in inputs:
            _, emitted = coordinator.observe(event, all_events)
            journals.extend(emitted)

        assert [str(journal.journal_id) for journal in journals] == vector["expected_journal_ids"]
        digests = tuple(
            (journal.accounting_content_digest, journal.lineage_digest) for journal in journals
        )
        digests_by_group.setdefault(vector["comparison_group"], []).append(digests)

    assert all(group[0] == group[1] for group in digests_by_group.values())


def test_case_lifecycle_vectors_use_live_registry(
    golden_fixture: dict[str, Any],
) -> None:
    run = GoldenScenarioRunner(golden_fixture).run()
    branch = DomainId("fraud-001")
    coordinator = run.engine.accounting_of(branch)
    all_events = {event.event_id: event for event in run.engine.events_of(branch)}
    successor = None

    for vector in golden_fixture["determinism_tests"]["case_lifecycle"]:
        action = vector["action"]
        if "case" in vector:
            case = coordinator.registry.get(vector["case"])
        if action == "repeat_input":
            event = next(iter(case.observed_inputs.values()))
            _, journals = coordinator.observe(event, all_events)
            assert journals == ()
            assert case.status.value == vector["expected_status"]
        elif action == "reverse":
            reversal_id = deterministic_id("journal", case.key, "reversal")
            assert case.reverse(reversal_id)
            assert case.status is AccountingCaseStatus.REVERSED
        elif action == "repeat_reverse":
            with pytest.raises(AccountingCaseError, match="AlreadyReversed"):
                case.reverse(deterministic_id("journal", case.key, "second-reversal"))
        elif action == "open_next_cycle":
            successor = coordinator.registry.open_next(case)
            assert successor.key.recognition_cycle == vector["expected_cycle"]
            assert successor.status.value == vector["expected_status"]
        elif action == "repeat_open_next_cycle":
            assert successor is not None
            assert coordinator.registry.open_next(case) is successor
        else:
            pytest.fail(f"unknown case lifecycle action: {action}")


def test_journal_posted_must_match_journal_case_key(
    golden_fixture: dict[str, Any],
) -> None:
    run = GoldenScenarioRunner(golden_fixture).run()
    result = run.steps["fraud-004"]
    posted = next(event for event in result.events if event.event_type.endswith("JournalPosted"))
    assert isinstance(posted.payload, JournalPosted)
    mutated = replace(
        posted,
        payload=JournalPosted(
            "wrong|accounting|case|key",
            posted.payload.journal_id,
            posted.payload.ledger_type,
        ),
    )
    journal = next(item for item in result.journals if item.journal_id == posted.payload.journal_id)
    state = run.engine.state_of(DomainId("fraud-001"))

    with pytest.raises(StateContractError, match="wrong accounting case key"):
        EventReducer.apply(state, mutated, {journal.journal_id: journal})
