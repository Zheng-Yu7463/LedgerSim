"""Four-layer state and the only production event reducer."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ledger_sim.domain.events import (
    AccountingCaseOpened,
    ControlTransferred,
    CustomerCommitmentEstablished,
    CustomerPaymentReceived,
    CustomerReceiptRecorded,
    DomainEvent,
    FraudDecisionRecorded,
    JournalPosted,
    PhysicalGoodsDispatched,
    SalesInvoiceIssued,
    SalesOrderCreated,
    SettlementRightEstablished,
    ShipmentRecordAccepted,
)
from ledger_sim.domain.values import (
    DomainId,
    Instant,
    Money,
    Quantity,
    QuantityBalance,
    UnitPrice,
)

if TYPE_CHECKING:
    from ledger_sim.domain.accounting import Journal


class StateContractError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CustomerCommitment:
    commitment_id: DomainId
    company_id: DomainId
    customer_id: DomainId
    product_id: DomainId
    quantity: Quantity
    fixed_consideration: Money
    currency: str
    established_at: Instant
    expires_at: Instant


@dataclass(frozen=True, slots=True)
class SalesOrder:
    business_chain_id: DomainId
    claimed_commitment_id: DomainId
    company_id: DomainId
    customer_id: DomainId
    product_id: DomainId
    quantity: Quantity
    unit_price: UnitPrice
    currency: str


@dataclass(frozen=True, slots=True)
class ShipmentRecord:
    shipment_id: DomainId
    business_chain_id: DomainId
    company_id: DomainId
    customer_id: DomainId
    product_id: DomainId
    quantity: Quantity


@dataclass(slots=True)
class SalesInvoice:
    invoice_id: DomainId
    business_chain_id: DomainId
    company_id: DomainId
    customer_id: DomainId
    product_id: DomainId
    quantity: Quantity
    net_amount: Money
    currency: str
    outstanding: Money


@dataclass(slots=True)
class SettlementRight:
    settlement_right_id: DomainId
    source_event_id: DomainId
    business_chain_id: DomainId
    customer_id: DomainId
    product_id: DomainId
    amount: Money
    currency: str
    outstanding: Money


@dataclass(slots=True)
class LedgerBalances:
    bank: Money
    accounts_receivable: Money
    inventory: Money
    paid_in_capital: Money
    sales_revenue: Money
    cost_of_goods_sold: Money
    profit: Money

    def apply(self, journal: Journal) -> None:
        normal_balance = {
            "bank": "debit",
            "accounts_receivable": "debit",
            "inventory": "debit",
            "paid_in_capital": "credit",
            "sales_revenue": "credit",
            "cost_of_goods_sold": "debit",
        }
        for line in journal.lines:
            try:
                direction = normal_balance[line.account]
            except KeyError as error:
                raise StateContractError(f"unknown account: {line.account}") from error
            effect = line.debit_amount - line.credit_amount
            if direction == "credit":
                effect = Money.zero() - effect
            setattr(self, line.account, getattr(self, line.account) + effect)
        self.profit = self.sales_revenue - self.cost_of_goods_sold

    def to_fixture(self) -> dict[str, str]:
        return {
            "bank": str(self.bank),
            "accounts_receivable": str(self.accounts_receivable),
            "inventory": str(self.inventory),
            "paid_in_capital": str(self.paid_in_capital),
            "sales_revenue": str(self.sales_revenue),
            "cost_of_goods_sold": str(self.cost_of_goods_sold),
            "profit": str(self.profit),
        }

    @classmethod
    def from_fixture(cls, raw: Mapping[str, Any]) -> LedgerBalances:
        return cls(
            bank=Money.parse(str(raw["bank"])),
            accounts_receivable=Money.parse(str(raw["accounts_receivable"])),
            inventory=Money.parse(str(raw["inventory"])),
            paid_in_capital=Money.parse(str(raw["paid_in_capital"])),
            sales_revenue=Money.parse(str(raw["sales_revenue"])),
            cost_of_goods_sold=Money.parse(str(raw["cost_of_goods_sold"])),
            profit=Money.parse(str(raw["profit"])),
        )


@dataclass(slots=True)
class EconomicState:
    physical_inventory_quantity: QuantityBalance
    bank: Money
    commitments: dict[DomainId, CustomerCommitment] = field(default_factory=dict)
    settlement_rights: dict[DomainId, SettlementRight] = field(default_factory=dict)


@dataclass(slots=True)
class EnterpriseState:
    recorded_inventory_quantity: QuantityBalance
    orders: dict[DomainId, SalesOrder] = field(default_factory=dict)
    shipments: dict[DomainId, ShipmentRecord] = field(default_factory=dict)
    invoices: dict[DomainId, SalesInvoice] = field(default_factory=dict)
    receipts: list[DomainId] = field(default_factory=list)


@dataclass(slots=True)
class TruthState:
    fraud_decisions: list[DomainId] = field(default_factory=list)


@dataclass(slots=True)
class FourLayerState:
    economic: EconomicState
    enterprise: EnterpriseState
    reported: LedgerBalances
    normative: LedgerBalances
    truth: TruthState = field(default_factory=TruthState)
    aggregate_versions: dict[DomainId, int] = field(default_factory=dict)

    @classmethod
    def from_opening_balances(cls, opening: Mapping[str, Any]) -> FourLayerState:
        state = cls(
            economic=EconomicState(
                QuantityBalance.parse(str(opening["physical_inventory_quantity"])),
                Money.parse(str(opening["normative"]["bank"])),
            ),
            enterprise=EnterpriseState(
                QuantityBalance.parse(str(opening["recorded_inventory_quantity"]))
            ),
            reported=LedgerBalances.from_fixture(opening["reported"]),
            normative=LedgerBalances.from_fixture(opening["normative"]),
        )
        state.assert_invariants()
        return state

    def version_of(self, aggregate_id: DomainId) -> int:
        return self.aggregate_versions.get(aggregate_id, 0)

    def bump_version(self, aggregate_id: DomainId) -> None:
        self.aggregate_versions[aggregate_id] = self.version_of(aggregate_id) + 1

    def to_fixture(self) -> dict[str, Any]:
        snapshot: dict[str, Any] = {
            "economic": {
                "physical_inventory_quantity": str(self.economic.physical_inventory_quantity),
                "commitments": [str(item) for item in self.economic.commitments],
                "settlement_rights": [str(item) for item in self.economic.settlement_rights],
                "bank": str(self.economic.bank),
            },
            "enterprise": {
                "orders": [str(item) for item in self.enterprise.orders],
                "shipments": [str(item) for item in self.enterprise.shipments],
                "invoices": [str(item) for item in self.enterprise.invoices],
                "receipts": [str(item) for item in self.enterprise.receipts],
                "recorded_inventory_quantity": str(self.enterprise.recorded_inventory_quantity),
            },
            "reported": self.reported.to_fixture(),
            "normative": self.normative.to_fixture(),
        }
        if self.truth.fraud_decisions:
            snapshot["truth"] = {
                "fraud_decisions": [str(item) for item in self.truth.fraud_decisions]
            }
        return snapshot

    def assert_invariants(self) -> None:
        for ledger_name, ledger in (
            ("reported", self.reported),
            ("normative", self.normative),
        ):
            assets = ledger.bank + ledger.accounts_receivable + ledger.inventory
            equity = ledger.paid_in_capital + ledger.profit
            if assets != equity:
                raise StateContractError(f"accounting equation failed for {ledger_name} ledger")


class EventReducer:
    @staticmethod
    def apply(
        state: FourLayerState,
        event: DomainEvent,
        journals: Mapping[DomainId, Journal],
    ) -> None:
        payload = event.payload
        if isinstance(payload, CustomerCommitmentEstablished):
            state.economic.commitments[payload.commitment_id] = CustomerCommitment(
                commitment_id=payload.commitment_id,
                company_id=payload.company_id,
                customer_id=payload.customer_id,
                product_id=payload.product_id,
                quantity=payload.quantity,
                fixed_consideration=payload.fixed_consideration,
                currency=payload.currency,
                established_at=event.committed_at,
                expires_at=payload.expires_at,
            )
        elif isinstance(payload, SalesOrderCreated):
            state.enterprise.orders[payload.business_chain_id] = SalesOrder(
                business_chain_id=payload.business_chain_id,
                claimed_commitment_id=payload.claimed_commitment_id,
                company_id=payload.company_id,
                customer_id=payload.customer_id,
                product_id=payload.product_id,
                quantity=payload.quantity,
                unit_price=payload.unit_price,
                currency=payload.currency,
            )
        elif isinstance(payload, PhysicalGoodsDispatched):
            state.economic.physical_inventory_quantity = (
                state.economic.physical_inventory_quantity.subtract(payload.quantity)
            )
        elif isinstance(payload, SettlementRightEstablished):
            state.economic.settlement_rights[payload.settlement_right_id] = SettlementRight(
                settlement_right_id=payload.settlement_right_id,
                source_event_id=event.event_id,
                business_chain_id=payload.business_chain_id,
                customer_id=payload.customer_id,
                product_id=payload.product_id,
                amount=payload.fixed_consideration,
                currency=payload.currency,
                outstanding=payload.fixed_consideration,
            )
        elif isinstance(payload, ShipmentRecordAccepted):
            state.enterprise.shipments[event.aggregate_id] = ShipmentRecord(
                shipment_id=event.aggregate_id,
                business_chain_id=payload.business_chain_id,
                company_id=payload.company_id,
                customer_id=payload.customer_id,
                product_id=payload.product_id,
                quantity=payload.quantity,
            )
            state.enterprise.recorded_inventory_quantity = (
                state.enterprise.recorded_inventory_quantity.subtract(payload.quantity)
            )
        elif isinstance(payload, SalesInvoiceIssued):
            state.enterprise.invoices[event.aggregate_id] = SalesInvoice(
                invoice_id=event.aggregate_id,
                business_chain_id=payload.business_chain_id,
                company_id=payload.company_id,
                customer_id=payload.customer_id,
                product_id=payload.product_id,
                quantity=payload.quantity,
                net_amount=payload.net_amount,
                currency=payload.currency,
                outstanding=payload.net_amount,
            )
        elif isinstance(payload, CustomerPaymentReceived):
            right = state.economic.settlement_rights[payload.settlement_right_id]
            right.outstanding = right.outstanding - payload.amount
            state.economic.bank = state.economic.bank + payload.amount
            if right.outstanding == Money.zero():
                del state.economic.settlement_rights[payload.settlement_right_id]
        elif isinstance(payload, CustomerReceiptRecorded):
            invoice = state.enterprise.invoices[payload.invoice_id]
            invoice.outstanding = invoice.outstanding - payload.amount
            state.enterprise.receipts.append(event.aggregate_id)
        elif isinstance(payload, JournalPosted):
            try:
                journal = journals[payload.journal_id]
            except KeyError as error:
                raise StateContractError(
                    f"journal event references missing journal: {payload.journal_id}"
                ) from error
            if journal.accounting_case_key != payload.accounting_case_key:
                raise StateContractError("journal event uses the wrong accounting case key")
            if journal.ledger_type != payload.ledger_type:
                raise StateContractError("journal event uses the wrong ledger type")
            ledger = state.reported if payload.ledger_type == "reported" else state.normative
            ledger.apply(journal)
        elif isinstance(payload, FraudDecisionRecorded):
            state.truth.fraud_decisions.append(event.aggregate_id)
        elif isinstance(payload, AccountingCaseOpened | ControlTransferred):
            pass
        else:
            raise StateContractError(f"unsupported event payload: {type(payload).__name__}")
        state.assert_invariants()
