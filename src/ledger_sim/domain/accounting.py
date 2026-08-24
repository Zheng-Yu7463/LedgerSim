"""Accounting case lifecycle and independent journal arithmetic."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from ledger_sim.domain.model import DomainEvent, Journal, money


class AccountingCaseStatus(StrEnum):
    PENDING = "pending"
    POSTED = "posted"
    REVERSED = "reversed"


class AccountingCaseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AccountingCaseKey:
    run_id: str
    branch_id: str
    ledger_type: str
    rule_id: str
    business_chain_id: str
    recognition_cycle: int

    @classmethod
    def parse(cls, value: str) -> AccountingCaseKey:
        parts = value.split("|")
        if len(parts) != 6:
            raise AccountingCaseError("accounting_case_key must contain six parts")
        cycle = int(parts[5])
        if cycle < 1:
            raise AccountingCaseError("recognition cycle must be positive")
        if parts[2] not in {"reported", "normative"}:
            raise AccountingCaseError("invalid ledger type")
        return cls(parts[0], parts[1], parts[2], parts[3], parts[4], cycle)

    def __str__(self) -> str:
        return "|".join(
            (
                self.run_id,
                self.branch_id,
                self.ledger_type,
                self.rule_id,
                self.business_chain_id,
                str(self.recognition_cycle),
            )
        )


@dataclass(slots=True)
class AccountingCase:
    key: AccountingCaseKey
    status: AccountingCaseStatus = AccountingCaseStatus.PENDING
    observed_inputs: set[tuple[str, str]] = field(default_factory=set)
    posted_journal_id: str | None = None
    reversal_journal_id: str | None = None

    def observe(self, event_id: str, input_role: str) -> bool:
        before = len(self.observed_inputs)
        self.observed_inputs.add((event_id, input_role))
        return len(self.observed_inputs) != before

    def post(self, journal_id: str) -> None:
        if self.status is AccountingCaseStatus.REVERSED:
            raise AccountingCaseError("cannot post a reversed accounting case")
        if self.status is AccountingCaseStatus.POSTED:
            if self.posted_journal_id == journal_id:
                return
            raise AccountingCaseError("accounting case already posted")
        self.posted_journal_id = journal_id
        self.status = AccountingCaseStatus.POSTED

    def reverse(self, reversal_journal_id: str) -> None:
        if self.status is AccountingCaseStatus.PENDING:
            raise AccountingCaseError("cannot reverse a pending accounting case")
        if self.status is AccountingCaseStatus.REVERSED:
            raise AccountingCaseError("AccountingCaseAlreadyReversed")
        self.reversal_journal_id = reversal_journal_id
        self.status = AccountingCaseStatus.REVERSED

    def reopen(self) -> AccountingCase:
        if self.status is not AccountingCaseStatus.REVERSED:
            raise AccountingCaseError("only a reversed case can open the next cycle")
        return AccountingCase(
            AccountingCaseKey(
                run_id=self.key.run_id,
                branch_id=self.key.branch_id,
                ledger_type=self.key.ledger_type,
                rule_id=self.key.rule_id,
                business_chain_id=self.key.business_chain_id,
                recognition_cycle=self.key.recognition_cycle + 1,
            )
        )


def _event_by_type(events: Iterable[DomainEvent], event_type: str) -> DomainEvent:
    matches = [event for event in events if event.event_type == event_type]
    if len(matches) != 1:
        raise AccountingCaseError(f"expected one {event_type}, found {len(matches)}")
    return matches[0]


def _rounded_cost(quantity_value: str, unit_cost: str) -> Decimal:
    return (Decimal(quantity_value) * Decimal(unit_cost)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def expected_account_amounts(
    journal: Journal, events_by_id: Mapping[str, DomainEvent]
) -> dict[str, tuple[Decimal, Decimal]]:
    key = AccountingCaseKey.parse(journal.accounting_case_key)
    inputs = [events_by_id[event_id] for event_id in journal.input_event_ids]

    if key.rule_id.endswith("sales_revenue_v1"):
        source_type = (
            "SalesInvoiceIssued" if key.ledger_type == "reported" else "SettlementRightEstablished"
        )
        source = _event_by_type(inputs, source_type)
        amount_field = "net_amount" if key.ledger_type == "reported" else "fixed_consideration"
        amount = money(str(source.payload[amount_field]))
        return {
            "accounts_receivable": (amount, money("0")),
            "sales_revenue": (money("0"), amount),
        }

    if key.rule_id.endswith("sales_cogs_v1"):
        if key.ledger_type == "reported":
            source = _event_by_type(inputs, "ShipmentRecordAccepted")
        else:
            control = _event_by_type(inputs, "ControlTransferred")
            dispatch_event_id = str(control.payload["dispatch_event_id"])
            try:
                source = events_by_id[dispatch_event_id]
            except KeyError as error:
                raise AccountingCaseError(
                    f"missing normative cost snapshot source: {dispatch_event_id}"
                ) from error
            if source.event_type != "PhysicalGoodsDispatched":
                raise AccountingCaseError("normative cost source is not a physical dispatch")
        amount = _rounded_cost(str(source.payload["quantity"]), str(source.payload["unit_cost"]))
        return {
            "cost_of_goods_sold": (amount, money("0")),
            "inventory": (money("0"), amount),
        }

    if key.rule_id.endswith("customer_payment_v1"):
        source_type = (
            "CustomerReceiptRecorded"
            if key.ledger_type == "reported"
            else "CustomerPaymentReceived"
        )
        source = _event_by_type(inputs, source_type)
        amount = money(str(source.payload["amount"]))
        return {
            "bank": (amount, money("0")),
            "accounts_receivable": (money("0"), amount),
        }

    raise AccountingCaseError(f"unsupported accounting rule: {key.rule_id}")


def validate_journal_semantics(journal: Journal, events_by_id: Mapping[str, DomainEvent]) -> None:
    expected = expected_account_amounts(journal, events_by_id)
    actual = {line.account: (line.debit_amount, line.credit_amount) for line in journal.lines}
    if actual != expected:
        raise AccountingCaseError(
            f"journal {journal.journal_id} differs from source-event arithmetic"
        )
