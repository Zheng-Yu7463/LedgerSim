"""Accounting coordinator that observes actual domain events and posts once."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date

from ledger_sim.domain.cases import (
    AccountingCase,
    AccountingCaseKey,
    AccountingCaseRegistry,
    AccountingCaseStatus,
)
from ledger_sim.domain.events import (
    AccountingCaseOpened,
    ControlTransferred,
    CustomerPaymentReceived,
    CustomerReceiptRecorded,
    DomainEvent,
    EventDraft,
    JournalPosted,
    PhysicalGoodsDispatched,
    SalesInvoiceIssued,
    SalesOrderCreated,
    SettlementRightEstablished,
    ShipmentRecordAccepted,
)
from ledger_sim.domain.values import DomainId, Money, deterministic_id


class AccountingContractError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class JournalLine:
    line_id: DomainId
    account: str
    debit_amount: Money
    credit_amount: Money

    def to_fixture(self) -> dict[str, str]:
        return {
            "line_id": str(self.line_id),
            "account": self.account,
            "debit_amount": str(self.debit_amount),
            "credit_amount": str(self.credit_amount),
        }


@dataclass(frozen=True, slots=True)
class InputLineage:
    input_role: str
    event_semantic_id: str

    def to_fixture(self) -> dict[str, str]:
        return {
            "input_role": self.input_role,
            "event_semantic_id": self.event_semantic_id,
        }


@dataclass(frozen=True, slots=True)
class Journal:
    journal_id: DomainId
    ledger_type: str
    accounting_case_key: str
    input_event_ids: tuple[DomainId, ...]
    input_lineage: tuple[InputLineage, ...]
    accounting_date: date
    lines: tuple[JournalLine, ...]
    accounting_content_digest: str
    lineage_digest: str

    def __post_init__(self) -> None:
        debits = sum(line.debit_amount.amount for line in self.lines)
        credits = sum(line.credit_amount.amount for line in self.lines)
        if debits != credits:
            raise AccountingContractError(f"unbalanced journal: {self.journal_id}")

    def to_fixture(self) -> dict[str, object]:
        return {
            "journal_id": str(self.journal_id),
            "ledger_type": self.ledger_type,
            "accounting_case_key": self.accounting_case_key,
            "input_event_ids": [str(item) for item in self.input_event_ids],
            "input_lineage": [item.to_fixture() for item in self.input_lineage],
            "accounting_date": self.accounting_date.isoformat(),
            "accounting_content_digest": self.accounting_content_digest,
            "lineage_digest": self.lineage_digest,
            "lines": [line.to_fixture() for line in self.lines],
        }


@dataclass(frozen=True, slots=True)
class AccountingRule:
    rule_id: str
    ledger_type: str
    required_roles: tuple[str, ...]
    journal_kind: str


SALES_RULES = (
    AccountingRule(
        "reported_sales_revenue_v1",
        "reported",
        ("shipment_record", "sales_invoice"),
        "revenue",
    ),
    AccountingRule(
        "reported_sales_cogs_v1",
        "reported",
        ("shipment_record", "sales_invoice"),
        "cogs",
    ),
    AccountingRule(
        "normative_sales_revenue_v1",
        "normative",
        ("control_transfer", "settlement_right"),
        "revenue",
    ),
    AccountingRule(
        "normative_sales_cogs_v1",
        "normative",
        ("control_transfer", "settlement_right"),
        "cogs",
    ),
)
PAYMENT_RULES = (
    AccountingRule(
        "normative_customer_payment_v1",
        "normative",
        ("customer_payment",),
        "payment",
    ),
    AccountingRule(
        "reported_customer_payment_v1",
        "reported",
        ("customer_receipt",),
        "payment",
    ),
)


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


class AccountingCoordinator:
    def __init__(self) -> None:
        self.registry = AccountingCaseRegistry()

    def observe(
        self,
        event: DomainEvent,
        all_events: dict[DomainId, DomainEvent],
    ) -> tuple[tuple[EventDraft, ...], tuple[Journal, ...]]:
        if isinstance(event.payload, SalesOrderCreated):
            return self._open_sales_cases(event), ()

        role = self._input_role(event)
        if role is None:
            return (), ()
        rules = self._rules_for_role(role)
        emitted: list[EventDraft] = []
        journals: list[Journal] = []
        chain_id = event.business_chain_id
        if chain_id is None:
            raise AccountingContractError(f"{event.event_type} lacks business_chain_id")
        for rule in rules:
            key = AccountingCaseKey(
                event.run_id,
                event.branch_id,
                rule.ledger_type,
                rule.rule_id,
                chain_id,
            )
            case, _ = self.registry.open(key, rule.required_roles)
            case.observe(role, event)
            if case.status is AccountingCaseStatus.PENDING and case.ready:
                journal = self._build_journal(case, rule, all_events)
                case.post(journal.journal_id)
                journals.append(journal)
                emitted.append(
                    EventDraft(
                        journal.journal_id,
                        JournalPosted(str(key), journal.journal_id, rule.ledger_type),
                    )
                )
        return tuple(emitted), tuple(journals)

    def _open_sales_cases(self, event: DomainEvent) -> tuple[EventDraft, ...]:
        chain_id = event.business_chain_id
        if chain_id is None:
            raise AccountingContractError("sales order event lacks business_chain_id")
        drafts: list[EventDraft] = []
        for rule in SALES_RULES:
            key = AccountingCaseKey(
                event.run_id,
                event.branch_id,
                rule.ledger_type,
                rule.rule_id,
                chain_id,
            )
            _, created = self.registry.open(key, rule.required_roles)
            if created:
                drafts.append(EventDraft(key.case_id, AccountingCaseOpened(str(key))))
        return tuple(drafts)

    @staticmethod
    def _input_role(event: DomainEvent) -> str | None:
        if isinstance(event.payload, ShipmentRecordAccepted):
            return "shipment_record"
        if isinstance(event.payload, SalesInvoiceIssued):
            return "sales_invoice"
        if isinstance(event.payload, ControlTransferred):
            return "control_transfer"
        if isinstance(event.payload, SettlementRightEstablished):
            return "settlement_right"
        if isinstance(event.payload, CustomerPaymentReceived):
            return "customer_payment"
        if isinstance(event.payload, CustomerReceiptRecorded):
            return "customer_receipt"
        return None

    @staticmethod
    def _rules_for_role(role: str) -> tuple[AccountingRule, ...]:
        rules = SALES_RULES + PAYMENT_RULES
        return tuple(rule for rule in rules if role in rule.required_roles)

    def _build_journal(
        self,
        case: AccountingCase,
        rule: AccountingRule,
        all_events: dict[DomainId, DomainEvent],
    ) -> Journal:
        inputs = tuple(case.observed_inputs[role] for role in rule.required_roles)
        self._assert_same_chain(inputs)
        amount, accounting_date = self._amount_and_date(rule, case, all_events)
        journal_id = deterministic_id("journal", case.key, "recognition")
        line_specs = self._line_specs(rule.journal_kind, amount)
        lines = tuple(
            JournalLine(
                deterministic_id(
                    "journal-line",
                    journal_id,
                    index,
                    account,
                    debit,
                    credit,
                ),
                account,
                debit,
                credit,
            )
            for index, (account, debit, credit) in enumerate(line_specs, start=1)
        )
        lineage = tuple(
            sorted(
                (
                    InputLineage(role, case.observed_inputs[role].semantic_id)
                    for role in rule.required_roles
                ),
                key=lambda item: (item.input_role, item.event_semantic_id),
            )
        )
        content = {
            "accounting_date": accounting_date.isoformat(),
            "accounting_period": accounting_date.isoformat()[:7],
            "currency": "CNY",
            "ledger_type": rule.ledger_type,
            "lines": sorted(
                (
                    {
                        "account": line.account,
                        "credit_amount": str(line.credit_amount),
                        "debit_amount": str(line.debit_amount),
                    }
                    for line in lines
                ),
                key=lambda line: (
                    line["account"],
                    line["debit_amount"],
                    line["credit_amount"],
                ),
            ),
            "rule_version": rule.rule_id,
        }
        lineage_value = [item.to_fixture() for item in lineage]
        return Journal(
            journal_id,
            rule.ledger_type,
            str(case.key),
            tuple(event.event_id for event in inputs),
            lineage,
            accounting_date,
            lines,
            _canonical_sha256(content),
            _canonical_sha256(lineage_value),
        )

    @staticmethod
    def _assert_same_chain(events: tuple[DomainEvent, ...]) -> None:
        chains = {event.business_chain_id for event in events}
        if len(chains) != 1:
            raise AccountingContractError("accounting inputs have different business chains")

    @staticmethod
    def _amount_and_date(
        rule: AccountingRule,
        case: AccountingCase,
        all_events: dict[DomainId, DomainEvent],
    ) -> tuple[Money, date]:
        inputs = case.observed_inputs
        if rule.journal_kind == "revenue":
            if rule.ledger_type == "reported":
                invoice = inputs["sales_invoice"].payload
                shipment = inputs["shipment_record"].payload
                if not isinstance(invoice, SalesInvoiceIssued) or not isinstance(
                    shipment, ShipmentRecordAccepted
                ):
                    raise AccountingContractError("invalid reported revenue inputs")
                if invoice.quantity != shipment.quantity:
                    raise AccountingContractError("reported revenue quantities differ")
                return invoice.net_amount, date.fromisoformat(invoice.invoice_date)
            control = inputs["control_transfer"].payload
            right = inputs["settlement_right"].payload
            if not isinstance(control, ControlTransferred) or not isinstance(
                right, SettlementRightEstablished
            ):
                raise AccountingContractError("invalid normative revenue inputs")
            if control.quantity != right.quantity:
                raise AccountingContractError("normative revenue quantities differ")
            dispatch = all_events[control.dispatch_event_id].payload
            if not isinstance(dispatch, PhysicalGoodsDispatched):
                raise AccountingContractError("control transfer does not reference dispatch")
            return right.fixed_consideration, dispatch.dispatched_at.value.date()
        if rule.journal_kind == "cogs":
            if rule.ledger_type == "reported":
                shipment = inputs["shipment_record"].payload
                invoice = inputs["sales_invoice"].payload
                if not isinstance(shipment, ShipmentRecordAccepted) or not isinstance(
                    invoice, SalesInvoiceIssued
                ):
                    raise AccountingContractError("invalid reported COGS inputs")
                if shipment.quantity != invoice.quantity:
                    raise AccountingContractError("reported COGS quantities differ")
                return shipment.unit_cost.total(shipment.quantity), date.fromisoformat(
                    invoice.invoice_date
                )
            control = inputs["control_transfer"].payload
            right = inputs["settlement_right"].payload
            if not isinstance(control, ControlTransferred) or not isinstance(
                right, SettlementRightEstablished
            ):
                raise AccountingContractError("invalid normative COGS inputs")
            if control.quantity != right.quantity:
                raise AccountingContractError("normative COGS quantities differ")
            dispatch = all_events[control.dispatch_event_id].payload
            if not isinstance(dispatch, PhysicalGoodsDispatched):
                raise AccountingContractError("normative COGS source is not dispatch")
            return dispatch.unit_cost.total(dispatch.quantity), dispatch.dispatched_at.value.date()
        if rule.journal_kind == "payment":
            role = rule.required_roles[0]
            payment_event = inputs[role]
            payload = payment_event.payload
            if isinstance(payload, CustomerPaymentReceived | CustomerReceiptRecorded):
                return payload.amount, payment_event.committed_at.value.date()
        raise AccountingContractError(f"unsupported journal rule: {rule.rule_id}")

    @staticmethod
    def _line_specs(
        journal_kind: str,
        amount: Money,
    ) -> tuple[tuple[str, Money, Money], ...]:
        zero = Money.zero()
        if journal_kind == "revenue":
            return (
                ("accounts_receivable", amount, zero),
                ("sales_revenue", zero, amount),
            )
        if journal_kind == "cogs":
            return (
                ("cost_of_goods_sold", amount, zero),
                ("inventory", zero, amount),
            )
        if journal_kind == "payment":
            return (
                ("bank", amount, zero),
                ("accounts_receivable", zero, amount),
            )
        raise AccountingContractError(f"unsupported journal kind: {journal_kind}")
