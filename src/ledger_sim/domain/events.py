"""Strong event payloads and deterministic event envelopes."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

from ledger_sim.domain.values import (
    DomainId,
    Instant,
    Money,
    Quantity,
    UnitCost,
    UnitPrice,
    deterministic_id,
)


@dataclass(frozen=True, slots=True)
class CustomerCommitmentEstablished:
    commitment_id: DomainId
    company_id: DomainId
    customer_id: DomainId
    product_id: DomainId
    quantity: Quantity
    fixed_consideration: Money
    currency: str
    delivery_term: str
    expires_at: Instant


@dataclass(frozen=True, slots=True)
class SalesOrderCreated:
    business_chain_id: DomainId
    claimed_commitment_id: DomainId
    company_id: DomainId
    customer_id: DomainId
    product_id: DomainId
    quantity: Quantity
    unit_price: UnitPrice
    currency: str


@dataclass(frozen=True, slots=True)
class AccountingCaseOpened:
    accounting_case_key: str


@dataclass(frozen=True, slots=True)
class PhysicalGoodsDispatched:
    business_chain_id: DomainId
    commitment_id: DomainId
    quantity: Quantity
    dispatched_at: Instant
    normative_cost_snapshot_id: DomainId
    unit_cost: UnitCost


@dataclass(frozen=True, slots=True)
class ControlTransferred:
    business_chain_id: DomainId
    commitment_id: DomainId
    dispatch_event_id: DomainId
    quantity: Quantity


@dataclass(frozen=True, slots=True)
class SettlementRightEstablished:
    settlement_right_id: DomainId
    business_chain_id: DomainId
    commitment_id: DomainId
    control_event_id: DomainId
    customer_id: DomainId
    product_id: DomainId
    quantity: Quantity
    fixed_consideration: Money
    currency: str


@dataclass(frozen=True, slots=True)
class ShipmentRecordAccepted:
    business_chain_id: DomainId
    company_id: DomainId
    customer_id: DomainId
    product_id: DomainId
    quantity: Quantity
    claimed_effective_at: Instant
    reported_cost_snapshot_id: DomainId
    unit_cost: UnitCost


@dataclass(frozen=True, slots=True)
class SalesInvoiceIssued:
    business_chain_id: DomainId
    company_id: DomainId
    customer_id: DomainId
    product_id: DomainId
    quantity: Quantity
    unit_price: UnitPrice
    net_amount: Money
    tax_amount: Money
    currency: str
    invoice_date: str


@dataclass(frozen=True, slots=True)
class CustomerPaymentReceived:
    business_chain_id: DomainId
    settlement_right_id: DomainId
    settlement_right_event_id: DomainId
    bank_account_id: DomainId
    amount: Money
    currency: str


@dataclass(frozen=True, slots=True)
class CustomerReceiptRecorded:
    business_chain_id: DomainId
    invoice_id: DomainId
    bank_account_id: DomainId
    amount: Money
    currency: str


@dataclass(frozen=True, slots=True)
class JournalPosted:
    accounting_case_key: str
    journal_id: DomainId
    ledger_type: str


@dataclass(frozen=True, slots=True)
class FraudDecisionRecorded:
    target_amount: Money
    target_period: str


type EventPayload = (
    CustomerCommitmentEstablished
    | SalesOrderCreated
    | AccountingCaseOpened
    | PhysicalGoodsDispatched
    | ControlTransferred
    | SettlementRightEstablished
    | ShipmentRecordAccepted
    | SalesInvoiceIssued
    | CustomerPaymentReceived
    | CustomerReceiptRecorded
    | JournalPosted
    | FraudDecisionRecorded
)


def event_type(payload: EventPayload) -> str:
    if isinstance(payload, JournalPosted):
        return (
            "ReportedJournalPosted"
            if payload.ledger_type == "reported"
            else "NormativeJournalPosted"
        )
    return type(payload).__name__


def _primitive(value: Any) -> Any:
    if isinstance(value, DomainId | Instant | Money | Quantity | UnitCost | UnitPrice):
        return str(value)
    if hasattr(value, "__dataclass_fields__"):
        return {field.name: _primitive(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_primitive(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class EventDraft:
    aggregate_id: DomainId
    payload: EventPayload


@dataclass(frozen=True, slots=True)
class DomainEvent:
    event_id: DomainId
    run_id: DomainId
    branch_id: DomainId
    aggregate_id: DomainId
    sequence_in_commit: int
    committed_at: Instant
    actor_id: DomainId
    causation_id: DomainId
    correlation_id: DomainId
    payload: EventPayload

    @property
    def event_type(self) -> str:
        return event_type(self.payload)

    @property
    def business_chain_id(self) -> DomainId | None:
        value = getattr(self.payload, "business_chain_id", None)
        return value if isinstance(value, DomainId) else None

    @property
    def semantic_id(self) -> str:
        chain = self.business_chain_id
        return f"{self.event_type}|{chain}" if chain is not None else self.event_type

    def to_fixture(self) -> dict[str, Any]:
        payload = _primitive(self.payload)
        if isinstance(self.payload, JournalPosted):
            payload.pop("ledger_type")
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "aggregate_id": str(self.aggregate_id),
            "sequence_in_commit": self.sequence_in_commit,
            "payload": payload,
        }


def envelope_event(
    draft: EventDraft,
    *,
    run_id: DomainId,
    branch_id: DomainId,
    command_id: DomainId,
    actor_id: DomainId,
    correlation_id: DomainId,
    committed_at: Instant,
    sequence_in_commit: int,
) -> DomainEvent:
    kind = event_type(draft.payload)
    identifier = deterministic_id(
        "event",
        run_id,
        branch_id,
        command_id,
        kind,
        sequence_in_commit,
    )
    return DomainEvent(
        event_id=identifier,
        run_id=run_id,
        branch_id=branch_id,
        aggregate_id=draft.aggregate_id,
        sequence_in_commit=sequence_in_commit,
        committed_at=committed_at,
        actor_id=actor_id,
        causation_id=command_id,
        correlation_id=correlation_id,
        payload=draft.payload,
    )
