"""In-memory accounting case registry used by the pure domain kernel."""

from __future__ import annotations

from ledger_sim.domain.accounting import AccountingCase, AccountingCaseError, AccountingCaseKey


class AccountingCaseRegistry:
    def __init__(self) -> None:
        self._cases: dict[str, AccountingCase] = {}
        self._successors: dict[str, str] = {}

    def open(self, key: AccountingCaseKey) -> AccountingCase:
        key_text = str(key)
        existing = self._cases.get(key_text)
        if existing is not None:
            return existing
        case = AccountingCase(key)
        self._cases[key_text] = case
        return case

    def open_next(self, predecessor: AccountingCase) -> AccountingCase:
        predecessor_key = str(predecessor.key)
        successor_key = self._successors.get(predecessor_key)
        if successor_key is not None:
            return self._cases[successor_key]
        if predecessor.reversal_journal_id is None:
            raise AccountingCaseError("only a reversed case can open the next cycle")
        successor = predecessor.reopen()
        successor_key = str(successor.key)
        self._cases[successor_key] = successor
        self._successors[predecessor_key] = successor_key
        return successor
