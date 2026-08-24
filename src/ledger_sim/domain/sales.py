"""Sales command-to-event semantic validation for the Phase 1A contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from ledger_sim.domain.model import DomainEvent, FourLayerState


class SalesContractError(ValueError):
    pass


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise SalesContractError("business instants must include a UTC offset")
    return parsed


def _event(events: Sequence[DomainEvent], event_type: str) -> DomainEvent:
    matches = [event for event in events if event.event_type == event_type]
    if len(matches) != 1:
        raise SalesContractError(f"expected one {event_type}, found {len(matches)}")
    return matches[0]


def _equal_fields(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    fields: Sequence[str],
    description: str,
) -> None:
    differences = {
        field: (left.get(field), right.get(field))
        for field in fields
        if left.get(field) != right.get(field)
    }
    if differences:
        raise SalesContractError(f"{description} fields differ: {differences}")


def validate_step_semantics(
    state: FourLayerState,
    step_branch_id: str,
    command: Mapping[str, Any],
    events: Sequence[DomainEvent],
) -> None:
    if command["branch_id"] != step_branch_id:
        raise SalesContractError("step and command branch differ")
    if [event.event_id for event in events] != list(
        dict.fromkeys(event.event_id for event in events)
    ):
        raise SalesContractError("step contains duplicate event IDs")

    command_type = str(command["command_type"])
    payload = command["payload"]
    aggregate_id = str(command["aggregate_id"])

    if command_type == "EstablishCustomerCommitment":
        established = _event(events, "CustomerCommitmentEstablished")
        _equal_fields(
            payload,
            established.payload,
            (
                "company_id",
                "customer_id",
                "product_id",
                "quantity",
                "fixed_consideration",
                "currency",
                "delivery_term",
                "expires_at",
            ),
            "customer commitment",
        )
        if established.payload["commitment_id"] != aggregate_id:
            raise SalesContractError("commitment ID must equal the target aggregate")
        if _instant(str(command["requested_at"])) >= _instant(str(payload["expires_at"])):
            raise SalesContractError("commitment must expire after establishment")
        return

    if command_type == "CreateSalesOrder":
        created = _event(events, "SalesOrderCreated")
        _equal_fields(
            payload, created.payload, ("quantity", "unit_price", "currency"), "sales order"
        )
        if created.payload["business_chain_id"] != aggregate_id:
            raise SalesContractError("sales order must create its business chain ID")
        return

    if command_type == "DispatchPhysicalGoods":
        commitment_id = str(payload["commitment_id"])
        try:
            commitment = state.economic.commitment_facts[commitment_id]
        except KeyError as error:
            raise SalesContractError(
                "EconomicFulfillmentMismatch: commitment does not exist"
            ) from error
        _equal_fields(
            payload,
            commitment,
            ("company_id", "customer_id", "product_id", "quantity", "currency"),
            "economic fulfillment",
        )
        dispatched_at = _instant(str(payload["dispatched_at"]))
        established_at = _instant(str(commitment["established_at"]))
        expires_at = _instant(str(commitment["expires_at"]))
        if not established_at <= dispatched_at < expires_at:
            raise SalesContractError("EconomicFulfillmentMismatch: commitment is not effective")

        dispatched = _event(events, "PhysicalGoodsDispatched")
        _equal_fields(
            payload,
            dispatched.payload,
            ("commitment_id", "quantity", "dispatched_at"),
            "physical dispatch",
        )
        control = _event(events, "ControlTransferred")
        if control.payload["dispatch_event_id"] != dispatched.event_id:
            raise SalesContractError("control transfer must reference the dispatch event")
        right = _event(events, "SettlementRightEstablished")
        if right.payload["control_event_id"] != control.event_id:
            raise SalesContractError("settlement right must reference the control transfer")
        if right.payload["fixed_consideration"] != commitment["fixed_consideration"]:
            raise SalesContractError("settlement right consideration differs from commitment")
        return

    if command_type == "RecordShipment":
        recorded = _event(events, "ShipmentRecordAccepted")
        _equal_fields(
            payload,
            recorded.payload,
            ("quantity", "claimed_effective_at"),
            "shipment record",
        )
        return

    if command_type == "IssueSalesInvoice":
        issued = _event(events, "SalesInvoiceIssued")
        _equal_fields(payload, issued.payload, ("quantity", "net_amount", "currency"), "invoice")
        calculated = Decimal(str(payload["quantity"])) * Decimal(str(payload["unit_price"]))
        if calculated.quantize(Decimal("0.01")) != Decimal(str(payload["net_amount"])):
            raise SalesContractError("invoice net amount differs from quantity times unit price")
        return

    if command_type == "ReceiveCustomerPayment":
        received = _event(events, "CustomerPaymentReceived")
        _equal_fields(
            payload,
            received.payload,
            ("settlement_right_id", "amount", "currency"),
            "customer payment",
        )
        return

    if command_type == "RecordCustomerReceipt":
        recorded = _event(events, "CustomerReceiptRecorded")
        _equal_fields(payload, recorded.payload, ("invoice_id", "amount", "currency"), "receipt")
        return

    if command_type == "RecordFraudDecision":
        decision = _event(events, "FraudDecisionRecorded")
        _equal_fields(
            payload, decision.payload, ("target_amount", "target_period"), "fraud decision"
        )
        return

    raise SalesContractError(f"unsupported command type: {command_type}")
