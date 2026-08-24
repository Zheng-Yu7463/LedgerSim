"""Golden event replay through the four fact layers."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ledger_sim.domain.accounting import validate_journal_semantics
from ledger_sim.domain.model import DomainEvent, FourLayerState, Journal, money, quantity
from ledger_sim.domain.sales import validate_step_semantics


class ReplayMismatch(AssertionError):
    pass


@dataclass(slots=True)
class ReplayResult:
    branches: dict[str, FourLayerState]
    events: dict[str, DomainEvent]


class GoldenReplay:
    def __init__(self, fixture: Mapping[str, Any]) -> None:
        self.fixture = fixture
        self.parents = {
            str(item["branch_id"]): item["parent_branch_id"] for item in fixture["branches"]
        }
        self.journals = {
            str(raw["journal_id"]): Journal.from_fixture(raw) for raw in fixture["journals"]
        }
        self.events: dict[str, DomainEvent] = {}
        self.branches: dict[str, FourLayerState] = {}

    def run(self) -> ReplayResult:
        root_ids = [branch_id for branch_id, parent in self.parents.items() if parent is None]
        if len(root_ids) != 1:
            raise ReplayMismatch("golden fixture must have exactly one root branch")
        root_id = root_ids[0]
        self.branches[root_id] = FourLayerState.from_fixture_opening(
            self.fixture["opening_balances"]
        )

        for step in self.fixture["steps"]:
            branch_id = str(step["branch_id"])
            state = self._branch_state(branch_id)
            committed_at = str(step["command"]["requested_at"])
            step_events = [
                DomainEvent.from_fixture(raw_event, committed_at)
                for raw_event in step["expected_events"]
            ]
            validate_step_semantics(state, branch_id, step["command"], step_events)
            for event in step_events:
                if event.event_id in self.events:
                    raise ReplayMismatch(f"duplicate event: {event.event_id}")
                self.events[event.event_id] = event
                self._evolve(state, event)

            state_ref = str(step["expected_state_ref"])
            expected = self.fixture["state_snapshots"][state_ref]
            actual = state.to_fixture()
            if actual != expected:
                raise ReplayMismatch(
                    f"state differs after {step['step_id']} ({state_ref}): "
                    f"actual={actual!r}, expected={expected!r}"
                )

        for journal in self.journals.values():
            validate_journal_semantics(journal, self.events)
        return ReplayResult(branches=self.branches, events=self.events)

    def _branch_state(self, branch_id: str) -> FourLayerState:
        if branch_id in self.branches:
            return self.branches[branch_id]
        parent_id = self.parents.get(branch_id)
        if parent_id is None or parent_id not in self.branches:
            raise ReplayMismatch(f"branch parent is unavailable: {branch_id}")
        self.branches[branch_id] = copy.deepcopy(self.branches[parent_id])
        return self.branches[branch_id]

    def _evolve(self, state: FourLayerState, event: DomainEvent) -> None:
        payload = event.payload
        event_type = event.event_type

        if event_type == "CustomerCommitmentEstablished":
            commitment_id = str(payload["commitment_id"])
            state.economic.commitments.append(commitment_id)
            state.economic.commitment_facts[commitment_id] = {
                **payload,
                "established_at": event.committed_at,
            }
        elif event_type == "SalesOrderCreated":
            state.enterprise.orders.append(str(payload["business_chain_id"]))
        elif event_type == "PhysicalGoodsDispatched":
            state.economic.physical_inventory_quantity -= quantity(str(payload["quantity"]))
        elif event_type == "SettlementRightEstablished":
            state.economic.settlement_rights.append(str(payload["settlement_right_id"]))
        elif event_type == "ShipmentRecordAccepted":
            state.enterprise.shipments.append(event.aggregate_id)
            state.enterprise.recorded_inventory_quantity -= quantity(str(payload["quantity"]))
        elif event_type == "SalesInvoiceIssued":
            state.enterprise.invoices.append(event.aggregate_id)
        elif event_type == "CustomerPaymentReceived":
            state.economic.bank += money(str(payload["amount"]))
            settlement_right_id = str(payload["settlement_right_id"])
            state.economic.settlement_rights.remove(settlement_right_id)
        elif event_type == "CustomerReceiptRecorded":
            state.enterprise.receipts.append(event.aggregate_id)
        elif event_type == "FraudDecisionRecorded":
            state.truth.fraud_decisions.append(event.aggregate_id)
        elif event_type in {"ReportedJournalPosted", "NormativeJournalPosted"}:
            journal = self.journals[str(payload["journal_id"])]
            ledger = state.reported if journal.ledger_type == "reported" else state.normative
            ledger.apply(journal)
        elif event_type in {"AccountingCaseOpened", "ControlTransferred"}:
            return
        else:
            raise ReplayMismatch(f"unsupported event type: {event_type}")

        self._assert_state_invariants(state)

    @staticmethod
    def _assert_state_invariants(state: FourLayerState) -> None:
        if state.economic.physical_inventory_quantity < Decimal():
            raise ReplayMismatch("physical inventory cannot be negative")
        if state.enterprise.recorded_inventory_quantity < Decimal():
            raise ReplayMismatch("recorded inventory cannot be negative")
        for ledger_name, ledger in (
            ("reported", state.reported),
            ("normative", state.normative),
        ):
            assets = ledger.bank + ledger.accounts_receivable + ledger.inventory
            equity = ledger.paid_in_capital + ledger.profit
            if assets != equity:
                raise ReplayMismatch(f"accounting equation failed for {ledger_name} ledger")
