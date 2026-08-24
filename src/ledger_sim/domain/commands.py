"""Versioned strong command codec. Raw mappings stop at parse_command()."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import date
from typing import Any, ClassVar

from ledger_sim.domain.values import (
    BusinessDate,
    DomainId,
    Instant,
    NonNegativeMoney,
    PositiveMoney,
    Quantity,
    UnitPrice,
)

COMMAND_SCHEMA_VERSION = "1.0.0"


class CommandCodecError(ValueError):
    pass


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
    fixed_consideration: PositiveMoney
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
    net_amount: PositiveMoney
    tax_amount: NonNegativeMoney
    currency: str
    invoice_date: BusinessDate


@dataclass(frozen=True, slots=True)
class IssueSalesInvoice(CommandEnvelope):
    command_type: ClassVar[str] = "IssueSalesInvoice"
    payload: InvoiceTerms


@dataclass(frozen=True, slots=True)
class PaymentTerms:
    settlement_right_id: DomainId
    bank_account_id: DomainId
    amount: PositiveMoney
    currency: str


@dataclass(frozen=True, slots=True)
class ReceiveCustomerPayment(CommandEnvelope):
    command_type: ClassVar[str] = "ReceiveCustomerPayment"
    payload: PaymentTerms


@dataclass(frozen=True, slots=True)
class ReceiptTerms:
    invoice_id: DomainId
    bank_account_id: DomainId
    amount: PositiveMoney
    currency: str


@dataclass(frozen=True, slots=True)
class RecordCustomerReceipt(CommandEnvelope):
    command_type: ClassVar[str] = "RecordCustomerReceipt"
    payload: ReceiptTerms


@dataclass(frozen=True, slots=True)
class FraudDecisionTerms:
    target_amount: PositiveMoney
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

_ENVELOPE_FIELDS = {
    "command_id",
    "schema_version",
    "run_id",
    "branch_id",
    "actor_id",
    "command_type",
    "requested_at",
    "aggregate_id",
    "expected_version",
    "business_chain_id",
    "correlation_id",
    "payload",
}
_PAYLOAD_FIELDS = {
    "EstablishCustomerCommitment": {
        "company_id",
        "customer_id",
        "product_id",
        "quantity",
        "fixed_consideration",
        "currency",
        "delivery_term",
        "expires_at",
    },
    "CreateSalesOrder": {
        "claimed_commitment_id",
        "company_id",
        "customer_id",
        "product_id",
        "quantity",
        "unit_price",
        "currency",
    },
    "DispatchPhysicalGoods": {
        "commitment_id",
        "company_id",
        "customer_id",
        "product_id",
        "quantity",
        "currency",
        "dispatched_at",
    },
    "RecordShipment": {
        "company_id",
        "customer_id",
        "product_id",
        "quantity",
        "claimed_effective_at",
    },
    "IssueSalesInvoice": {
        "company_id",
        "customer_id",
        "product_id",
        "quantity",
        "unit_price",
        "net_amount",
        "tax_amount",
        "currency",
        "invoice_date",
    },
    "ReceiveCustomerPayment": {
        "settlement_right_id",
        "bank_account_id",
        "amount",
        "currency",
    },
    "RecordCustomerReceipt": {
        "invoice_id",
        "bank_account_id",
        "amount",
        "currency",
    },
    "RecordFraudDecision": {"target_amount", "target_period"},
}


def _exact_fields(raw: Mapping[str, Any], expected: set[str], location: str) -> None:
    if any(not isinstance(key, str) for key in raw):
        raise CommandCodecError(f"{location} field names must be strings")
    actual = set(raw)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise CommandCodecError(f"{location} fields differ: missing={missing}, extra={extra}")


def _string(raw: Mapping[str, Any], key: str, location: str) -> str:
    value = raw[key]
    if not isinstance(value, str) or not value:
        raise CommandCodecError(f"{location}.{key} must be a non-empty string")
    return value


def _canonical_value[ValueT](
    raw: Mapping[str, Any],
    key: str,
    location: str,
    parser: Callable[[str], ValueT],
) -> ValueT:
    text = _string(raw, key, location)
    try:
        value = parser(text)
    except (ArithmeticError, ValueError) as error:
        raise CommandCodecError(f"{location}.{key} is invalid") from error
    if str(value) != text:
        raise CommandCodecError(f"{location}.{key} is not canonical")
    return value


def _payload(raw: Mapping[str, Any], command_type: str) -> Mapping[str, Any]:
    value = raw["payload"]
    if not isinstance(value, Mapping):
        raise CommandCodecError("command.payload must be an object")
    _exact_fields(value, _PAYLOAD_FIELDS[command_type], f"{command_type}.payload")
    for key in value:
        _string(value, key, f"{command_type}.payload")
    return value


def _target_period(raw: Mapping[str, Any], key: str, location: str) -> str:
    value = _string(raw, key, location)
    try:
        parsed = date.fromisoformat(f"{value}-01")
    except ValueError as error:
        raise CommandCodecError(f"{location}.{key} is invalid") from error
    if value != parsed.strftime("%Y-%m"):
        raise CommandCodecError(f"{location}.{key} is not canonical")
    return value


def _base(raw: Mapping[str, Any]) -> dict[str, Any]:
    expected_version = raw["expected_version"]
    if (
        not isinstance(expected_version, int)
        or isinstance(expected_version, bool)
        or expected_version < 0
    ):
        raise CommandCodecError("command.expected_version must be a non-negative integer")
    business_chain = raw["business_chain_id"]
    if business_chain is not None and (not isinstance(business_chain, str) or not business_chain):
        raise CommandCodecError("command.business_chain_id must be null or a non-empty string")
    return {
        "command_id": DomainId(_string(raw, "command_id", "command")),
        "schema_version": _string(raw, "schema_version", "command"),
        "run_id": DomainId(_string(raw, "run_id", "command")),
        "branch_id": DomainId(_string(raw, "branch_id", "command")),
        "actor_id": DomainId(_string(raw, "actor_id", "command")),
        "requested_at": _canonical_value(raw, "requested_at", "command", Instant.parse),
        "aggregate_id": DomainId(_string(raw, "aggregate_id", "command")),
        "expected_version": expected_version,
        "business_chain_id": DomainId(business_chain) if business_chain is not None else None,
        "correlation_id": DomainId(_string(raw, "correlation_id", "command")),
    }


class CommandCodec:
    @staticmethod
    def decode(raw: object) -> Command:
        if not isinstance(raw, Mapping):
            raise CommandCodecError("command must be an object")
        _exact_fields(raw, _ENVELOPE_FIELDS, "command")
        schema_version = _string(raw, "schema_version", "command")
        if schema_version != COMMAND_SCHEMA_VERSION:
            raise CommandCodecError(f"unsupported command schema version: {schema_version}")
        command_type = _string(raw, "command_type", "command")
        if command_type not in _PAYLOAD_FIELDS:
            raise CommandCodecError(f"unsupported command type: {command_type}")
        payload = _payload(raw, command_type)
        base = _base(raw)

        if command_type == EstablishCustomerCommitment.command_type:
            return EstablishCustomerCommitment(
                **base,
                payload=CommitmentTerms(
                    DomainId(_string(payload, "company_id", command_type)),
                    DomainId(_string(payload, "customer_id", command_type)),
                    DomainId(_string(payload, "product_id", command_type)),
                    _canonical_value(payload, "quantity", command_type, Quantity.parse),
                    _canonical_value(
                        payload,
                        "fixed_consideration",
                        command_type,
                        PositiveMoney.parse,
                    ),
                    _string(payload, "currency", command_type),
                    _string(payload, "delivery_term", command_type),
                    _canonical_value(payload, "expires_at", command_type, Instant.parse),
                ),
            )
        if command_type == CreateSalesOrder.command_type:
            return CreateSalesOrder(
                **base,
                payload=SalesOrderTerms(
                    DomainId(_string(payload, "claimed_commitment_id", command_type)),
                    DomainId(_string(payload, "company_id", command_type)),
                    DomainId(_string(payload, "customer_id", command_type)),
                    DomainId(_string(payload, "product_id", command_type)),
                    _canonical_value(payload, "quantity", command_type, Quantity.parse),
                    _canonical_value(payload, "unit_price", command_type, UnitPrice.parse),
                    _string(payload, "currency", command_type),
                ),
            )
        if command_type == DispatchPhysicalGoods.command_type:
            return DispatchPhysicalGoods(
                **base,
                payload=DispatchTerms(
                    DomainId(_string(payload, "commitment_id", command_type)),
                    DomainId(_string(payload, "company_id", command_type)),
                    DomainId(_string(payload, "customer_id", command_type)),
                    DomainId(_string(payload, "product_id", command_type)),
                    _canonical_value(payload, "quantity", command_type, Quantity.parse),
                    _string(payload, "currency", command_type),
                    _canonical_value(payload, "dispatched_at", command_type, Instant.parse),
                ),
            )
        if command_type == RecordShipment.command_type:
            return RecordShipment(
                **base,
                payload=ShipmentTerms(
                    DomainId(_string(payload, "company_id", command_type)),
                    DomainId(_string(payload, "customer_id", command_type)),
                    DomainId(_string(payload, "product_id", command_type)),
                    _canonical_value(payload, "quantity", command_type, Quantity.parse),
                    _canonical_value(
                        payload,
                        "claimed_effective_at",
                        command_type,
                        Instant.parse,
                    ),
                ),
            )
        if command_type == IssueSalesInvoice.command_type:
            return IssueSalesInvoice(
                **base,
                payload=InvoiceTerms(
                    DomainId(_string(payload, "company_id", command_type)),
                    DomainId(_string(payload, "customer_id", command_type)),
                    DomainId(_string(payload, "product_id", command_type)),
                    _canonical_value(payload, "quantity", command_type, Quantity.parse),
                    _canonical_value(payload, "unit_price", command_type, UnitPrice.parse),
                    _canonical_value(payload, "net_amount", command_type, PositiveMoney.parse),
                    _canonical_value(payload, "tax_amount", command_type, NonNegativeMoney.parse),
                    _string(payload, "currency", command_type),
                    _canonical_value(payload, "invoice_date", command_type, BusinessDate.parse),
                ),
            )
        if command_type == ReceiveCustomerPayment.command_type:
            return ReceiveCustomerPayment(
                **base,
                payload=PaymentTerms(
                    DomainId(_string(payload, "settlement_right_id", command_type)),
                    DomainId(_string(payload, "bank_account_id", command_type)),
                    _canonical_value(payload, "amount", command_type, PositiveMoney.parse),
                    _string(payload, "currency", command_type),
                ),
            )
        if command_type == RecordCustomerReceipt.command_type:
            return RecordCustomerReceipt(
                **base,
                payload=ReceiptTerms(
                    DomainId(_string(payload, "invoice_id", command_type)),
                    DomainId(_string(payload, "bank_account_id", command_type)),
                    _canonical_value(payload, "amount", command_type, PositiveMoney.parse),
                    _string(payload, "currency", command_type),
                ),
            )
        if command_type == RecordFraudDecision.command_type:
            return RecordFraudDecision(
                **base,
                payload=FraudDecisionTerms(
                    _canonical_value(payload, "target_amount", command_type, PositiveMoney.parse),
                    _target_period(payload, "target_period", command_type),
                ),
            )
        raise AssertionError("command type registry and decoder are inconsistent")


def parse_command(raw: object) -> Command:
    return CommandCodec.decode(raw)


def command_primitive(command: Command) -> dict[str, Any]:
    def normalize(value: Any) -> Any:
        if isinstance(
            value,
            BusinessDate
            | DomainId
            | Instant
            | NonNegativeMoney
            | PositiveMoney
            | Quantity
            | UnitPrice,
        ):
            return str(value)
        if is_dataclass(value) and not isinstance(value, type):
            return {field.name: normalize(getattr(value, field.name)) for field in fields(value)}
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        return value

    normalized = normalize(command)
    if not isinstance(normalized, dict):
        raise TypeError("command must normalize to an object")
    normalized["command_type"] = command.command_type
    return normalized
