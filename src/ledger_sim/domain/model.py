"""Core immutable event and accounting value types."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

MONEY_PLACES = Decimal("0.01")
QUANTITY_PLACES = Decimal("0.0001")


def money(value: str | Decimal) -> Decimal:
    return Decimal(value).quantize(MONEY_PLACES)


def quantity(value: str | Decimal) -> Decimal:
    return Decimal(value).quantize(QUANTITY_PLACES)


def money_text(value: Decimal) -> str:
    return format(value.quantize(MONEY_PLACES), ".2f")


def quantity_text(value: Decimal) -> str:
    return format(value.quantize(QUANTITY_PLACES), ".4f")


@dataclass(frozen=True, slots=True)
class DomainEvent:
    event_id: str
    event_type: str
    aggregate_id: str
    payload: Mapping[str, Any]
    committed_at: str

    @classmethod
    def from_fixture(cls, raw: Mapping[str, Any], committed_at: str) -> DomainEvent:
        return cls(
            event_id=str(raw["event_id"]),
            event_type=str(raw["event_type"]),
            aggregate_id=str(raw["aggregate_id"]),
            payload=dict(raw["payload"]),
            committed_at=committed_at,
        )


@dataclass(frozen=True, slots=True)
class JournalLine:
    line_id: str
    account: str
    debit_amount: Decimal
    credit_amount: Decimal

    @classmethod
    def from_fixture(cls, raw: Mapping[str, Any]) -> JournalLine:
        line = cls(
            line_id=str(raw["line_id"]),
            account=str(raw["account"]),
            debit_amount=money(str(raw["debit_amount"])),
            credit_amount=money(str(raw["credit_amount"])),
        )
        if (line.debit_amount > 0) == (line.credit_amount > 0):
            raise ValueError(f"journal line must have exactly one positive side: {line.line_id}")
        return line


@dataclass(frozen=True, slots=True)
class Journal:
    journal_id: str
    ledger_type: str
    accounting_case_key: str
    input_event_ids: tuple[str, ...]
    accounting_date: str
    lines: tuple[JournalLine, ...]

    @classmethod
    def from_fixture(cls, raw: Mapping[str, Any]) -> Journal:
        journal = cls(
            journal_id=str(raw["journal_id"]),
            ledger_type=str(raw["ledger_type"]),
            accounting_case_key=str(raw["accounting_case_key"]),
            input_event_ids=tuple(str(item) for item in raw["input_event_ids"]),
            accounting_date=str(raw["accounting_date"]),
            lines=tuple(JournalLine.from_fixture(line) for line in raw["lines"]),
        )
        if sum((line.debit_amount for line in journal.lines), Decimal()) != sum(
            (line.credit_amount for line in journal.lines), Decimal()
        ):
            raise ValueError(f"unbalanced journal: {journal.journal_id}")
        return journal


@dataclass(slots=True)
class LedgerBalances:
    bank: Decimal
    accounts_receivable: Decimal
    inventory: Decimal
    paid_in_capital: Decimal
    sales_revenue: Decimal
    cost_of_goods_sold: Decimal
    profit: Decimal

    @classmethod
    def from_fixture(cls, raw: Mapping[str, Any]) -> LedgerBalances:
        return cls(**{name: money(str(value)) for name, value in raw.items()})

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
            if line.account not in normal_balance:
                raise ValueError(f"unknown account: {line.account}")
            effect = line.debit_amount - line.credit_amount
            if normal_balance[line.account] == "credit":
                effect = -effect
            setattr(self, line.account, getattr(self, line.account) + effect)
        self.profit = self.sales_revenue - self.cost_of_goods_sold

    def to_fixture(self) -> dict[str, str]:
        return {
            "bank": money_text(self.bank),
            "accounts_receivable": money_text(self.accounts_receivable),
            "inventory": money_text(self.inventory),
            "paid_in_capital": money_text(self.paid_in_capital),
            "sales_revenue": money_text(self.sales_revenue),
            "cost_of_goods_sold": money_text(self.cost_of_goods_sold),
            "profit": money_text(self.profit),
        }


@dataclass(slots=True)
class EconomicState:
    physical_inventory_quantity: Decimal
    commitments: list[str] = field(default_factory=list)
    settlement_rights: list[str] = field(default_factory=list)
    bank: Decimal = Decimal("0.00")
    commitment_facts: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(slots=True)
class EnterpriseState:
    orders: list[str] = field(default_factory=list)
    shipments: list[str] = field(default_factory=list)
    invoices: list[str] = field(default_factory=list)
    receipts: list[str] = field(default_factory=list)
    recorded_inventory_quantity: Decimal = Decimal("0.0000")


@dataclass(slots=True)
class TruthState:
    fraud_decisions: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FourLayerState:
    economic: EconomicState
    enterprise: EnterpriseState
    reported: LedgerBalances
    normative: LedgerBalances
    truth: TruthState = field(default_factory=TruthState)

    @classmethod
    def from_fixture_opening(cls, opening: Mapping[str, Any]) -> FourLayerState:
        return cls(
            economic=EconomicState(
                physical_inventory_quantity=quantity(str(opening["physical_inventory_quantity"])),
                bank=money(str(opening["normative"]["bank"])),
            ),
            enterprise=EnterpriseState(
                recorded_inventory_quantity=quantity(str(opening["recorded_inventory_quantity"]))
            ),
            reported=LedgerBalances.from_fixture(opening["reported"]),
            normative=LedgerBalances.from_fixture(opening["normative"]),
        )

    def to_fixture(self) -> dict[str, Any]:
        snapshot: dict[str, Any] = {
            "economic": {
                "physical_inventory_quantity": quantity_text(
                    self.economic.physical_inventory_quantity
                ),
                "commitments": list(self.economic.commitments),
                "settlement_rights": list(self.economic.settlement_rights),
                "bank": money_text(self.economic.bank),
            },
            "enterprise": {
                "orders": list(self.enterprise.orders),
                "shipments": list(self.enterprise.shipments),
                "invoices": list(self.enterprise.invoices),
                "receipts": list(self.enterprise.receipts),
                "recorded_inventory_quantity": quantity_text(
                    self.enterprise.recorded_inventory_quantity
                ),
            },
            "reported": self.reported.to_fixture(),
            "normative": self.normative.to_fixture(),
        }
        if self.truth.fraud_decisions:
            snapshot["truth"] = {"fraud_decisions": list(self.truth.fraud_decisions)}
        return snapshot
