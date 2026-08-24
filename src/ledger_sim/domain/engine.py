"""The sole command execution entry point for the Phase 1A domain kernel."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from ledger_sim.domain.accounting import AccountingCoordinator, Journal
from ledger_sim.domain.commands import Command
from ledger_sim.domain.events import DomainEvent, EventDraft, envelope_event
from ledger_sim.domain.idempotency import IdempotencyRegistry
from ledger_sim.domain.sales import SalesAggregate, SalesPolicy
from ledger_sim.domain.state import EventReducer, FourLayerState
from ledger_sim.domain.values import DomainId


class EngineContractError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    command_id: DomainId
    events: tuple[DomainEvent, ...]
    journals: tuple[Journal, ...]


@dataclass(slots=True)
class BranchRuntime:
    state: FourLayerState
    accounting: AccountingCoordinator = field(default_factory=AccountingCoordinator)
    events: dict[DomainId, DomainEvent] = field(default_factory=dict)
    journals: dict[DomainId, Journal] = field(default_factory=dict)


_ALLOWED_EVENT_ORDERS: dict[str, tuple[str, ...]] = {
    "EstablishCustomerCommitment": ("CustomerCommitmentEstablished",),
    "CreateSalesOrder": (
        "SalesOrderCreated",
        "AccountingCaseOpened",
        "AccountingCaseOpened",
        "AccountingCaseOpened",
        "AccountingCaseOpened",
    ),
    "DispatchPhysicalGoods": (
        "PhysicalGoodsDispatched",
        "ControlTransferred",
        "SettlementRightEstablished",
        "NormativeJournalPosted",
        "NormativeJournalPosted",
    ),
    "RecordShipment": ("ShipmentRecordAccepted",),
    "IssueSalesInvoice": (
        "SalesInvoiceIssued",
        "ReportedJournalPosted",
        "ReportedJournalPosted",
    ),
    "ReceiveCustomerPayment": (
        "CustomerPaymentReceived",
        "NormativeJournalPosted",
    ),
    "RecordCustomerReceipt": (
        "CustomerReceiptRecorded",
        "ReportedJournalPosted",
    ),
    "RecordFraudDecision": ("FraudDecisionRecorded",),
}


class DomainEngine:
    def __init__(
        self,
        *,
        run_id: DomainId,
        root_branch_id: DomainId,
        opening_state: FourLayerState,
        sales_policy: SalesPolicy,
    ) -> None:
        self.run_id = run_id
        self.sales = SalesAggregate(sales_policy)
        self._branches = {root_branch_id: BranchRuntime(copy.deepcopy(opening_state))}
        self._idempotency: IdempotencyRegistry[ExecutionResult] = IdempotencyRegistry()

    def handle(self, command: Command) -> ExecutionResult:
        if command.run_id != self.run_id:
            raise EngineContractError("command run differs from engine run")
        previous = self._idempotency.find(command)
        if previous is not None:
            return previous

        try:
            current = self._branches[command.branch_id]
        except KeyError as error:
            raise EngineContractError(f"unknown branch: {command.branch_id}") from error

        working = copy.deepcopy(current)
        drafts = self.sales.decide(command, working.state)
        accepted_events: list[DomainEvent] = []
        accepted_journals: list[Journal] = []

        for draft in drafts:
            event = self._accept_draft(
                working,
                command,
                draft,
                len(accepted_events) + 1,
            )
            accepted_events.append(event)
            accounting_drafts, journals = working.accounting.observe(
                event,
                working.events,
            )
            for journal in journals:
                if journal.journal_id in working.journals:
                    raise EngineContractError(f"duplicate journal: {journal.journal_id}")
                working.journals[journal.journal_id] = journal
                accepted_journals.append(journal)
            for accounting_draft in accounting_drafts:
                accounting_event = self._accept_draft(
                    working,
                    command,
                    accounting_draft,
                    len(accepted_events) + 1,
                )
                accepted_events.append(accounting_event)

        actual_order = tuple(event.event_type for event in accepted_events)
        expected_order = _ALLOWED_EVENT_ORDERS[command.command_type]
        if actual_order != expected_order:
            raise EngineContractError(
                f"{command.command_type} emitted {actual_order}, expected {expected_order}"
            )

        working.state.bump_version(command.aggregate_id)
        result = ExecutionResult(
            command.command_id,
            tuple(accepted_events),
            tuple(accepted_journals),
        )
        self._idempotency.register(command, result)
        self._branches[command.branch_id] = working
        return result

    @staticmethod
    def _accept_draft(
        runtime: BranchRuntime,
        command: Command,
        draft: EventDraft,
        sequence_in_commit: int,
    ) -> DomainEvent:
        event = envelope_event(
            draft,
            run_id=command.run_id,
            branch_id=command.branch_id,
            command_id=command.command_id,
            actor_id=command.actor_id,
            correlation_id=command.correlation_id,
            committed_at=command.requested_at,
            sequence_in_commit=sequence_in_commit,
        )
        if event.event_id in runtime.events:
            raise EngineContractError(f"duplicate event: {event.event_id}")
        runtime.events[event.event_id] = event
        EventReducer.apply(runtime.state, event, runtime.journals)
        return event

    def fork_for_test(self, parent_branch_id: DomainId, child_branch_id: DomainId) -> None:
        if child_branch_id in self._branches:
            raise EngineContractError(f"branch already exists: {child_branch_id}")
        try:
            parent = self._branches[parent_branch_id]
        except KeyError as error:
            raise EngineContractError(f"unknown parent branch: {parent_branch_id}") from error
        self._branches[child_branch_id] = copy.deepcopy(parent)

    def state_of(self, branch_id: DomainId) -> FourLayerState:
        try:
            return copy.deepcopy(self._branches[branch_id].state)
        except KeyError as error:
            raise EngineContractError(f"unknown branch: {branch_id}") from error

    def events_of(self, branch_id: DomainId) -> tuple[DomainEvent, ...]:
        try:
            return tuple(self._branches[branch_id].events.values())
        except KeyError as error:
            raise EngineContractError(f"unknown branch: {branch_id}") from error

    def journals_of(self, branch_id: DomainId) -> tuple[Journal, ...]:
        try:
            return tuple(self._branches[branch_id].journals.values())
        except KeyError as error:
            raise EngineContractError(f"unknown branch: {branch_id}") from error

    def accounting_of(self, branch_id: DomainId) -> AccountingCoordinator:
        try:
            return self._branches[branch_id].accounting
        except KeyError as error:
            raise EngineContractError(f"unknown branch: {branch_id}") from error
