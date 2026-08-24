"""Accounting case lifecycle and input registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ledger_sim.domain.events import DomainEvent
from ledger_sim.domain.values import DomainId, deterministic_id


class AccountingCaseStatus(StrEnum):
    PENDING = "pending"
    POSTED = "posted"
    REVERSED = "reversed"


class AccountingCaseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AccountingCaseKey:
    run_id: DomainId
    branch_id: DomainId
    ledger_type: str
    rule_id: str
    business_chain_id: DomainId
    recognition_cycle: int = 1

    @classmethod
    def parse(cls, value: str) -> AccountingCaseKey:
        parts = value.split("|")
        if len(parts) != 6:
            raise AccountingCaseError("accounting_case_key must contain six parts")
        cycle = int(parts[5])
        if cycle < 1 or parts[2] not in {"reported", "normative"}:
            raise AccountingCaseError("invalid accounting case key")
        return cls(
            DomainId(parts[0]),
            DomainId(parts[1]),
            parts[2],
            parts[3],
            DomainId(parts[4]),
            cycle,
        )

    @property
    def case_id(self) -> DomainId:
        return deterministic_id("accounting-case", self)

    def next_cycle(self) -> AccountingCaseKey:
        return AccountingCaseKey(
            self.run_id,
            self.branch_id,
            self.ledger_type,
            self.rule_id,
            self.business_chain_id,
            self.recognition_cycle + 1,
        )

    def __str__(self) -> str:
        return "|".join(
            (
                str(self.run_id),
                str(self.branch_id),
                self.ledger_type,
                self.rule_id,
                str(self.business_chain_id),
                str(self.recognition_cycle),
            )
        )


@dataclass(slots=True)
class AccountingCase:
    key: AccountingCaseKey
    required_roles: tuple[str, ...]
    status: AccountingCaseStatus = AccountingCaseStatus.PENDING
    observed_inputs: dict[str, DomainEvent] = field(default_factory=dict)
    posted_journal_id: DomainId | None = None
    reversal_journal_id: DomainId | None = None

    def observe(self, role: str, event: DomainEvent) -> bool:
        if role not in self.required_roles:
            raise AccountingCaseError(f"unexpected input role {role} for {self.key.rule_id}")
        existing = self.observed_inputs.get(role)
        if existing is not None:
            if existing.event_id != event.event_id:
                raise AccountingCaseError(f"role {role} already has a different event")
            return False
        self.observed_inputs[role] = event
        return True

    @property
    def ready(self) -> bool:
        return all(role in self.observed_inputs for role in self.required_roles)

    def post(self, journal_id: DomainId) -> bool:
        if self.status is AccountingCaseStatus.REVERSED:
            raise AccountingCaseError("cannot post a reversed accounting case")
        if self.status is AccountingCaseStatus.POSTED:
            if self.posted_journal_id != journal_id:
                raise AccountingCaseError("accounting case already posted")
            return False
        if not self.ready:
            raise AccountingCaseError("cannot post before all required roles are present")
        self.posted_journal_id = journal_id
        self.status = AccountingCaseStatus.POSTED
        return True

    def reverse(self, reversal_journal_id: DomainId) -> bool:
        if self.status is AccountingCaseStatus.PENDING:
            raise AccountingCaseError("cannot reverse a pending accounting case")
        if self.status is AccountingCaseStatus.REVERSED:
            raise AccountingCaseError("AccountingCaseAlreadyReversed")
        self.reversal_journal_id = reversal_journal_id
        self.status = AccountingCaseStatus.REVERSED
        return True


class AccountingCaseRegistry:
    def __init__(self) -> None:
        self._cases: dict[str, AccountingCase] = {}
        self._successors: dict[str, str] = {}

    @property
    def cases(self) -> tuple[AccountingCase, ...]:
        return tuple(self._cases.values())

    def open(
        self,
        key: AccountingCaseKey,
        required_roles: tuple[str, ...],
    ) -> tuple[AccountingCase, bool]:
        key_text = str(key)
        existing = self._cases.get(key_text)
        if existing is not None:
            if existing.required_roles != required_roles:
                raise AccountingCaseError("case reopened with different required roles")
            return existing, False
        case = AccountingCase(key, required_roles)
        self._cases[key_text] = case
        return case, True

    def get(self, key: AccountingCaseKey | str) -> AccountingCase:
        key_text = str(key)
        try:
            return self._cases[key_text]
        except KeyError as error:
            raise AccountingCaseError(f"missing accounting case: {key_text}") from error

    def open_next(self, predecessor: AccountingCase) -> AccountingCase:
        predecessor_key = str(predecessor.key)
        successor_key = self._successors.get(predecessor_key)
        if successor_key is not None:
            return self._cases[successor_key]
        if predecessor.status is not AccountingCaseStatus.REVERSED:
            raise AccountingCaseError("only a reversed case can open the next cycle")
        successor, _ = self.open(predecessor.key.next_cycle(), predecessor.required_roles)
        self._successors[predecessor_key] = str(successor.key)
        return successor
