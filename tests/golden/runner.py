"""Golden scenario orchestration with no domain rules or expected-event replay."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ledger_sim.domain.commands import parse_command
from ledger_sim.domain.engine import DomainEngine, ExecutionResult
from ledger_sim.domain.sales import SalesPolicy
from ledger_sim.domain.state import FourLayerState
from ledger_sim.domain.values import DomainId


class GoldenMismatch(AssertionError):
    pass


@dataclass(frozen=True, slots=True)
class GoldenRunResult:
    engine: DomainEngine
    steps: dict[str, ExecutionResult]


class GoldenScenarioRunner:
    def __init__(self, fixture: dict[str, Any]) -> None:
        self.fixture = fixture

    def run(self) -> GoldenRunResult:
        root_id, child_ids = self._branch_ids()
        master = self.fixture["master_data"]
        engine = DomainEngine(
            run_id=DomainId(str(self.fixture["run_id"])),
            root_branch_id=root_id,
            opening_state=FourLayerState.from_opening_balances(self.fixture["opening_balances"]),
            sales_policy=SalesPolicy(
                DomainId(str(master["company_id"])),
                DomainId(str(master["customer_id"])),
                DomainId(str(master["product_id"])),
                str(master["currency"]),
            ),
        )
        expected_journals = {
            str(journal["journal_id"]): journal
            for journal in self.fixture["journals"]
            if journal["journal_role"] == "recognition"
        }
        seen_journal_ids: set[str] = set()
        results: dict[str, ExecutionResult] = {}
        fork_after = str(self.fixture["fork_after_step_id"])
        did_fork = False

        for step in self.fixture["steps"]:
            step_id = str(step["step_id"])
            command = parse_command(step["command"])
            if command.branch_id != DomainId(str(step["branch_id"])):
                raise GoldenMismatch(f"step and command branches differ: {step_id}")
            if did_fork and command.branch_id == root_id:
                raise GoldenMismatch(f"ancestor command appears after fork point: {step_id}")

            result = engine.handle(command)
            results[step_id] = result
            actual_events = [event.to_fixture() for event in result.events]
            if actual_events != step["expected_events"]:
                raise GoldenMismatch(
                    f"events differ after {step_id}: "
                    f"actual={actual_events!r}, expected={step['expected_events']!r}"
                )

            for journal in result.journals:
                expected = expected_journals.get(str(journal.journal_id))
                if expected is None:
                    raise GoldenMismatch(
                        f"unexpected journal after {step_id}: {journal.journal_id}"
                    )
                seen_journal_ids.add(str(journal.journal_id))
                actual = journal.to_fixture()
                if actual != expected:
                    raise GoldenMismatch(
                        f"journal differs after {step_id}: actual={actual!r}, expected={expected!r}"
                    )

            expected_state = self.fixture["state_snapshots"][step["expected_state_ref"]]
            actual_state = engine.state_of(command.branch_id).to_fixture()
            if actual_state != expected_state:
                raise GoldenMismatch(
                    f"state differs after {step_id}: "
                    f"actual={actual_state!r}, expected={expected_state!r}"
                )

            if step_id == fork_after:
                for child_id in child_ids:
                    engine.fork_for_test(root_id, child_id)
                did_fork = True

        if seen_journal_ids != set(expected_journals):
            raise GoldenMismatch("actual and expected journal sets differ")
        for expected in self.fixture["pending_cases"]:
            key = expected["accounting_case_key"]
            branch_id = DomainId(str(key).split("|")[1])
            case = engine.accounting_of(branch_id).registry.get(str(key))
            actual = {
                "accounting_case_key": str(case.key),
                "status": case.status.value,
                "observed_input_event_ids": [
                    str(event.event_id) for event in case.observed_inputs.values()
                ],
                "evaluation_count": len(case.observed_inputs),
                "journal_count": int(case.posted_journal_id is not None),
            }
            if actual != expected:
                raise GoldenMismatch(
                    f"pending accounting case differs: actual={actual!r}, expected={expected!r}"
                )
        if not did_fork:
            raise GoldenMismatch(f"fork step was not executed: {fork_after}")
        return GoldenRunResult(engine, results)

    def _branch_ids(self) -> tuple[DomainId, tuple[DomainId, ...]]:
        roots = [
            DomainId(str(branch["branch_id"]))
            for branch in self.fixture["branches"]
            if branch["parent_branch_id"] is None
        ]
        if len(roots) != 1:
            raise GoldenMismatch("fixture must define exactly one root branch")
        root = roots[0]
        children = tuple(
            DomainId(str(branch["branch_id"]))
            for branch in self.fixture["branches"]
            if branch["parent_branch_id"] == str(root)
        )
        if not children:
            raise GoldenMismatch("fixture must define test child branches")
        return root, children
