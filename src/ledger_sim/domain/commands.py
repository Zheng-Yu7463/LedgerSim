"""Strong command contracts. Raw mappings stop at parse_command()."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import date
from typing import Any, ClassVar

from ledger_sim.domain.values import DomainId, Instant, Money, Quantity, UnitPrice


@dataclass(frozen=True, slots=True)
class CommandEnvelope:
    command_id: DomainId
    schema_version: str
    run_id: DomainId
    branch_id: DomainId
    actor_id: DomainId
    requested_at: Instant
    aggregate_id: DomainId
    expected_version: int
    business_chain_id: DomainId | None
    correlation_id: DomainId

    command_type: ClassVar[str]


@dataclass(frozen=True, slots=True)
class CommitmentTerms:
    company_id: DomainId
    customer_id: DomainId
    product_id: DomainId
    quantity: Quantity
    fixed_consideration: Money
    currency: str
    delivery_term: str
    expires_at: Instant


@dataclass(frozen=True, slots=True)
class EstablishCustomerCommitment(CommandEnvelope):
    command_type: ClassVar[str] = "EstablishCustomerCommitment"
    payload: CommitmentTerms


@dataclass(frozen=True, slots=True)
class SalesOrderTerms:
    claimed_commitment_id: DomainId
    company_id: DomainId
    customer_id: DomainId
    product_id: DomainId
    quantity: Quantity
    unit_price: UnitPrice
    currency: str


@dataclass(frozen=True, slots=True)
class CreateSalesOrder(CommandEnvelope):
    command_type: ClassVar[str] = "CreateSalesOrder"
    payload: SalesOrderTerms


@dataclass(frozen=True, slots=True)
class DispatchTerms:
    commitment_id: DomainId
    company_id: DomainId
    customer_id: DomainId
    product_id: DomainId
    quantity: Quantity
    currency: str
    dispatched_at: Instant


@dataclass(frozen=True, slots=True)
class DispatchPhysicalGoods(CommandEnvelope):
    command_type: ClassVar[str] = "DispatchPhysicalGoods"
    payload: DispatchTerms


@dataclass(frozen=True, slots=True)
class ShipmentTerms:
    company_id: DomainId
    customer_id: DomainId
    product_id: DomainId
    quantity: Quantity
    claimed_effective_at: Instant


@dataclass(frozen=True, slots=True)
class RecordShipment(CommandEnvelope):
    command_type: ClassVar[str] = "RecordShipment"
    payload: ShipmentTerms


@dataclass(frozen=True, slots=True)
class InvoiceTerms:
    company_id: DomainId
    customer_id: DomainId
    product_id: DomainId
    quantity: Quantity
    unit_price: UnitPrice
    net_amount: Money
    tax_amount: Money
    currency: str
    invoice_date: date


@dataclass(frozen=True, slots=True)
class IssueSalesInvoice(CommandEnvelope):
    command_type: ClassVar[str] = "IssueSalesInvoice"
    payload: InvoiceTerms


@dataclass(frozen=True, slots=True)
class PaymentTerms:
    settlement_right_id: DomainId
    bank_account_id: DomainId
    amount: Money
    currency: str


@dataclass(frozen=True, slots=True)
class ReceiveCustomerPayment(CommandEnvelope):
    command_type: ClassVar[str] = "ReceiveCustomerPayment"
    payload: PaymentTerms


@dataclass(frozen=True, slots=True)
class ReceiptTerms:
    invoice_id: DomainId
    bank_account_id: DomainId
    amount: Money
    currency: str


@dataclass(frozen=True, slots=True)
class RecordCustomerReceipt(CommandEnvelope):
    command_type: ClassVar[str] = "RecordCustomerReceipt"
    payload: ReceiptTerms


@dataclass(frozen=True, slots=True)
class FraudDecisionTerms:
    target_amount: Money
    target_period: str


@dataclass(frozen=True, slots=True)
class RecordFraudDecision(CommandEnvelope):
    command_type: ClassVar[str] = "RecordFraudDecision"
    payload: FraudDecisionTerms


type Command = (
    EstablishCustomerCommitment
    | CreateSalesOrder
    | DispatchPhysicalGoods
    | RecordShipment
    | IssueSalesInvoice
    | ReceiveCustomerPayment
    | RecordCustomerReceipt
    | RecordFraudDecision
)


def _base(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "command_id": DomainId(str(raw["command_id"])),
        "schema_version": str(raw["schema_version"]),
        "run_id": DomainId(str(raw["run_id"])),
        "branch_id": DomainId(str(raw["branch_id"])),
        "actor_id": DomainId(str(raw["actor_id"])),
        "requested_at": Instant.parse(str(raw["requested_at"])),
        "aggregate_id": DomainId(str(raw["aggregate_id"])),
        "expected_version": int(raw["expected_version"]),
        "business_chain_id": (
            DomainId(str(raw["business_chain_id"]))
            if raw["business_chain_id"] is not None
            else None
        ),
        "correlation_id": DomainId(str(raw["correlation_id"])),
    }


def parse_command(raw: Mapping[str, Any]) -> Command:
    payload = raw["payload"]
    if not isinstance(payload, Mapping):
        raise TypeError("command payload must be an object")
    base = _base(raw)
    command_type = str(raw["command_type"])

    if command_type == EstablishCustomerCommitment.command_type:
        return EstablishCustomerCommitment(
            **base,
            payload=CommitmentTerms(
                DomainId(str(payload["company_id"])),
                DomainId(str(payload["customer_id"])),
                DomainId(str(payload["product_id"])),
                Quantity.parse(str(payload["quantity"])),
                Money.parse(str(payload["fixed_consideration"])),
                str(payload["currency"]),
                str(payload["delivery_term"]),
                Instant.parse(str(payload["expires_at"])),
            ),
        )
    if command_type == CreateSalesOrder.command_type:
        return CreateSalesOrder(
            **base,
            payload=SalesOrderTerms(
                DomainId(str(payload["claimed_commitment_id"])),
                DomainId(str(payload["company_id"])),
                DomainId(str(payload["customer_id"])),
                DomainId(str(payload["product_id"])),
                Quantity.parse(str(payload["quantity"])),
                UnitPrice.parse(str(payload["unit_price"])),
                str(payload["currency"]),
            ),
        )
    if command_type == DispatchPhysicalGoods.command_type:
        return DispatchPhysicalGoods(
            **base,
            payload=DispatchTerms(
                DomainId(str(payload["commitment_id"])),
                DomainId(str(payload["company_id"])),
                DomainId(str(payload["customer_id"])),
                DomainId(str(payload["product_id"])),
                Quantity.parse(str(payload["quantity"])),
                str(payload["currency"]),
                Instant.parse(str(payload["dispatched_at"])),
            ),
        )
    if command_type == RecordShipment.command_type:
        return RecordShipment(
            **base,
            payload=ShipmentTerms(
                DomainId(str(payload["company_id"])),
                DomainId(str(payload["customer_id"])),
                DomainId(str(payload["product_id"])),
                Quantity.parse(str(payload["quantity"])),
                Instant.parse(str(payload["claimed_effective_at"])),
            ),
        )
    if command_type == IssueSalesInvoice.command_type:
        return IssueSalesInvoice(
            **base,
            payload=InvoiceTerms(
                DomainId(str(payload["company_id"])),
                DomainId(str(payload["customer_id"])),
                DomainId(str(payload["product_id"])),
                Quantity.parse(str(payload["quantity"])),
                UnitPrice.parse(str(payload["unit_price"])),
                Money.parse(str(payload["net_amount"])),
                Money.parse(str(payload["tax_amount"])),
                str(payload["currency"]),
                date.fromisoformat(str(payload["invoice_date"])),
            ),
        )
    if command_type == ReceiveCustomerPayment.command_type:
        return ReceiveCustomerPayment(
            **base,
            payload=PaymentTerms(
                DomainId(str(payload["settlement_right_id"])),
                DomainId(str(payload["bank_account_id"])),
                Money.parse(str(payload["amount"])),
                str(payload["currency"]),
            ),
        )
    if command_type == RecordCustomerReceipt.command_type:
        return RecordCustomerReceipt(
            **base,
            payload=ReceiptTerms(
                DomainId(str(payload["invoice_id"])),
                DomainId(str(payload["bank_account_id"])),
                Money.parse(str(payload["amount"])),
                str(payload["currency"]),
            ),
        )
    if command_type == RecordFraudDecision.command_type:
        return RecordFraudDecision(
            **base,
            payload=FraudDecisionTerms(
                Money.parse(str(payload["target_amount"])),
                str(payload["target_period"]),
            ),
        )
    raise ValueError(f"unsupported command type: {command_type}")


def command_primitive(command: Command) -> dict[str, Any]:
    def normalize(value: Any) -> Any:
        if isinstance(value, DomainId | Instant | Money | Quantity | UnitPrice):
            return str(value)
        if isinstance(value, date):
            return value.isoformat()
        if is_dataclass(value) and not isinstance(value, type):
            return {field.name: normalize(getattr(value, field.name)) for field in fields(value)}
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        return value

    raw = normalize(command)
    if not isinstance(raw, dict):
        raise TypeError("command must normalize to an object")
    raw["command_type"] = command.command_type
    return raw
