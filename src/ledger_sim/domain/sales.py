"""Sales aggregate command decisions for the Phase 1A vertical slice."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ledger_sim.domain.commands import (
    Command,
    CreateSalesOrder,
    DispatchPhysicalGoods,
    EstablishCustomerCommitment,
    IssueSalesInvoice,
    ReceiveCustomerPayment,
    RecordCustomerReceipt,
    RecordFraudDecision,
    RecordShipment,
)
from ledger_sim.domain.events import (
    ControlTransferred,
    CustomerCommitmentEstablished,
    CustomerPaymentReceived,
    CustomerReceiptRecorded,
    EventDraft,
    FraudDecisionRecorded,
    PhysicalGoodsDispatched,
    SalesInvoiceIssued,
    SalesOrderCreated,
    SettlementRightEstablished,
    ShipmentRecordAccepted,
)
from ledger_sim.domain.state import FourLayerState
from ledger_sim.domain.values import (
    DomainId,
    Money,
    UnitCost,
    deterministic_id,
)


class SalesContractError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SalesPolicy:
    company_id: DomainId
    customer_id: DomainId
    product_id: DomainId
    currency: str


class SalesAggregate:
    def __init__(self, policy: SalesPolicy) -> None:
        self.policy = policy

    def decide(self, command: Command, state: FourLayerState) -> tuple[EventDraft, ...]:
        actual_version = state.version_of(command.aggregate_id)
        if command.expected_version != actual_version:
            raise SalesContractError(
                f"expected version {command.expected_version}, actual {actual_version}"
            )
        if isinstance(command, EstablishCustomerCommitment):
            return self._establish(command, state)
        if isinstance(command, CreateSalesOrder):
            return self._create_order(command, state)
        if isinstance(command, DispatchPhysicalGoods):
            return self._dispatch(command, state)
        if isinstance(command, RecordShipment):
            return self._record_shipment(command, state)
        if isinstance(command, IssueSalesInvoice):
            return self._issue_invoice(command, state)
        if isinstance(command, ReceiveCustomerPayment):
            return self._receive_payment(command, state)
        if isinstance(command, RecordCustomerReceipt):
            return self._record_receipt(command, state)
        if isinstance(command, RecordFraudDecision):
            return (
                EventDraft(
                    command.aggregate_id,
                    FraudDecisionRecorded(
                        command.payload.target_amount,
                        command.payload.target_period,
                    ),
                ),
            )
        raise SalesContractError(f"unsupported command: {type(command).__name__}")

    def _validate_master(
        self,
        company_id: DomainId,
        customer_id: DomainId,
        product_id: DomainId,
        currency: str,
    ) -> None:
        expected = (
            self.policy.company_id,
            self.policy.customer_id,
            self.policy.product_id,
            self.policy.currency,
        )
        actual = (company_id, customer_id, product_id, currency)
        if actual != expected:
            raise SalesContractError("company, customer, product, or currency differs")

    def _establish(
        self,
        command: EstablishCustomerCommitment,
        state: FourLayerState,
    ) -> tuple[EventDraft, ...]:
        terms = command.payload
        self._validate_master(
            terms.company_id,
            terms.customer_id,
            terms.product_id,
            terms.currency,
        )
        if command.aggregate_id in state.economic.commitments:
            raise SalesContractError("customer commitment already exists")
        if terms.delivery_term != "dispatch_point":
            raise SalesContractError("unsupported delivery term")
        if terms.fixed_consideration <= Money.zero():
            raise SalesContractError("consideration must be positive")
        if command.requested_at >= terms.expires_at:
            raise SalesContractError("commitment must expire after establishment")
        return (
            EventDraft(
                command.aggregate_id,
                CustomerCommitmentEstablished(
                    command.aggregate_id,
                    terms.company_id,
                    terms.customer_id,
                    terms.product_id,
                    terms.quantity,
                    terms.fixed_consideration,
                    terms.currency,
                    terms.delivery_term,
                    terms.expires_at,
                ),
            ),
        )

    def _create_order(
        self,
        command: CreateSalesOrder,
        state: FourLayerState,
    ) -> tuple[EventDraft, ...]:
        terms = command.payload
        self._validate_master(
            terms.company_id,
            terms.customer_id,
            terms.product_id,
            terms.currency,
        )
        if command.business_chain_id is not None:
            raise SalesContractError("new order command cannot supply a business chain ID")
        if command.aggregate_id in state.enterprise.orders:
            raise SalesContractError("sales order already exists")
        commitment = state.economic.commitments.get(terms.claimed_commitment_id)
        if commitment is not None and (
            commitment.company_id != terms.company_id
            or commitment.customer_id != terms.customer_id
            or commitment.product_id != terms.product_id
            or commitment.quantity != terms.quantity
            or commitment.fixed_consideration != terms.unit_price.total(terms.quantity)
            or commitment.currency != terms.currency
        ):
            raise SalesContractError("sales order differs from its claimed commitment")
        return (
            EventDraft(
                command.aggregate_id,
                SalesOrderCreated(
                    command.aggregate_id,
                    terms.claimed_commitment_id,
                    terms.company_id,
                    terms.customer_id,
                    terms.product_id,
                    terms.quantity,
                    terms.unit_price,
                    terms.currency,
                ),
            ),
        )

    def _dispatch(
        self,
        command: DispatchPhysicalGoods,
        state: FourLayerState,
    ) -> tuple[EventDraft, ...]:
        terms = command.payload
        chain_id = self._required_chain(command)
        commitment = state.economic.commitments.get(terms.commitment_id)
        order = state.enterprise.orders.get(chain_id)
        if commitment is None or order is None:
            raise SalesContractError("EconomicFulfillmentMismatch: missing commitment or order")
        self._validate_master(
            terms.company_id,
            terms.customer_id,
            terms.product_id,
            terms.currency,
        )
        if (
            terms.company_id != commitment.company_id
            or terms.customer_id != commitment.customer_id
            or terms.product_id != commitment.product_id
            or terms.quantity != commitment.quantity
            or terms.currency != commitment.currency
            or terms.quantity != order.quantity
            or order.unit_price.total(order.quantity) != commitment.fixed_consideration
        ):
            raise SalesContractError("EconomicFulfillmentMismatch")
        if not commitment.established_at <= terms.dispatched_at < commitment.expires_at:
            raise SalesContractError("EconomicFulfillmentMismatch: commitment is not effective")
        if state.economic.physical_inventory_quantity.amount < terms.quantity.amount:
            raise SalesContractError("insufficient physical inventory")

        unit_cost = self._unit_cost(
            state.normative.inventory,
            state.economic.physical_inventory_quantity.amount,
        )
        dispatch_id = deterministic_id(
            "event",
            command.run_id,
            command.branch_id,
            command.command_id,
            "PhysicalGoodsDispatched",
            1,
        )
        control_id = deterministic_id(
            "event",
            command.run_id,
            command.branch_id,
            command.command_id,
            "ControlTransferred",
            2,
        )
        settlement_right_id = deterministic_id(
            "settlement-right",
            command.run_id,
            command.branch_id,
            chain_id,
            1,
        )
        return (
            EventDraft(
                command.aggregate_id,
                PhysicalGoodsDispatched(
                    chain_id,
                    terms.commitment_id,
                    terms.quantity,
                    terms.dispatched_at,
                    deterministic_id(
                        "cost-snapshot",
                        "normative",
                        command.run_id,
                        command.branch_id,
                        chain_id,
                        1,
                    ),
                    unit_cost,
                ),
            ),
            EventDraft(
                terms.commitment_id,
                ControlTransferred(
                    chain_id,
                    terms.commitment_id,
                    dispatch_id,
                    terms.quantity,
                ),
            ),
            EventDraft(
                terms.commitment_id,
                SettlementRightEstablished(
                    settlement_right_id,
                    chain_id,
                    terms.commitment_id,
                    control_id,
                    terms.customer_id,
                    terms.product_id,
                    terms.quantity,
                    commitment.fixed_consideration,
                    terms.currency,
                ),
            ),
        )

    def _record_shipment(
        self,
        command: RecordShipment,
        state: FourLayerState,
    ) -> tuple[EventDraft, ...]:
        terms = command.payload
        chain_id = self._required_chain(command)
        order = state.enterprise.orders.get(chain_id)
        if order is None:
            raise SalesContractError("shipment references a missing business chain")
        if (
            terms.company_id != order.company_id
            or terms.customer_id != order.customer_id
            or terms.product_id != order.product_id
            or terms.quantity != order.quantity
        ):
            raise SalesContractError("shipment differs from its sales order")
        if state.enterprise.recorded_inventory_quantity.amount < terms.quantity.amount:
            raise SalesContractError("insufficient recorded inventory")
        unit_cost = self._unit_cost(
            state.reported.inventory,
            state.enterprise.recorded_inventory_quantity.amount,
        )
        return (
            EventDraft(
                command.aggregate_id,
                ShipmentRecordAccepted(
                    chain_id,
                    terms.company_id,
                    terms.customer_id,
                    terms.product_id,
                    terms.quantity,
                    terms.claimed_effective_at,
                    deterministic_id(
                        "cost-snapshot",
                        "reported",
                        command.run_id,
                        command.branch_id,
                        chain_id,
                        1,
                    ),
                    unit_cost,
                ),
            ),
        )

    def _issue_invoice(
        self,
        command: IssueSalesInvoice,
        state: FourLayerState,
    ) -> tuple[EventDraft, ...]:
        terms = command.payload
        chain_id = self._required_chain(command)
        order = state.enterprise.orders.get(chain_id)
        if order is None:
            raise SalesContractError("invoice references a missing business chain")
        shipment = next(
            (
                item
                for item in state.enterprise.shipments.values()
                if item.business_chain_id == chain_id
            ),
            None,
        )
        if shipment is None:
            raise SalesContractError("invoice requires an accepted shipment record")
        if (
            terms.company_id != order.company_id
            or terms.customer_id != order.customer_id
            or terms.product_id != order.product_id
            or terms.quantity != order.quantity
            or terms.unit_price != order.unit_price
            or terms.currency != order.currency
        ):
            raise SalesContractError("invoice differs from its sales order")
        if terms.net_amount != terms.unit_price.total(terms.quantity):
            raise SalesContractError("invoice amount differs from quantity times unit price")
        if terms.tax_amount != Money.zero():
            raise SalesContractError("Phase 1A tax amount must be zero")
        return (
            EventDraft(
                command.aggregate_id,
                SalesInvoiceIssued(
                    chain_id,
                    terms.company_id,
                    terms.customer_id,
                    terms.product_id,
                    terms.quantity,
                    terms.unit_price,
                    terms.net_amount,
                    terms.tax_amount,
                    terms.currency,
                    terms.invoice_date.isoformat(),
                ),
            ),
        )

    def _receive_payment(
        self,
        command: ReceiveCustomerPayment,
        state: FourLayerState,
    ) -> tuple[EventDraft, ...]:
        terms = command.payload
        chain_id = self._required_chain(command)
        right = state.economic.settlement_rights.get(terms.settlement_right_id)
        if right is None or right.business_chain_id != chain_id:
            raise SalesContractError("payment references a missing settlement right")
        if terms.currency != right.currency or terms.amount > right.outstanding:
            raise SalesContractError("payment exceeds or differs from settlement right")
        return (
            EventDraft(
                command.aggregate_id,
                CustomerPaymentReceived(
                    chain_id,
                    terms.settlement_right_id,
                    right.source_event_id,
                    terms.bank_account_id,
                    terms.amount,
                    terms.currency,
                ),
            ),
        )

    def _record_receipt(
        self,
        command: RecordCustomerReceipt,
        state: FourLayerState,
    ) -> tuple[EventDraft, ...]:
        terms = command.payload
        chain_id = self._required_chain(command)
        invoice = state.enterprise.invoices.get(terms.invoice_id)
        if invoice is None or invoice.business_chain_id != chain_id:
            raise SalesContractError("receipt references a missing invoice")
        if terms.currency != invoice.currency or terms.amount > invoice.outstanding:
            raise SalesContractError("receipt exceeds or differs from invoice")
        return (
            EventDraft(
                command.aggregate_id,
                CustomerReceiptRecorded(
                    chain_id,
                    terms.invoice_id,
                    terms.bank_account_id,
                    terms.amount,
                    terms.currency,
                ),
            ),
        )

    @staticmethod
    def _required_chain(command: Command) -> DomainId:
        if command.business_chain_id is None:
            raise SalesContractError("command requires business_chain_id")
        return command.business_chain_id

    @staticmethod
    def _unit_cost(inventory: Money, quantity: Decimal) -> UnitCost:
        if quantity <= 0:
            raise SalesContractError("cannot derive cost from empty inventory")
        return UnitCost.parse(inventory.amount / quantity)
