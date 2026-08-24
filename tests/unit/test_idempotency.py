from __future__ import annotations

import copy
from typing import Any

import pytest

from ledger_sim.domain.idempotency import CommandIdConflict, IdempotencyRegistry


def _set_path(target: dict[str, Any], dotted_path: str, value: Any) -> None:
    parts = dotted_path.split(".")
    current: dict[str, Any] = target
    for part in parts[:-1]:
        current = current[part]
    current[parts[-1]] = value


def test_fixture_retry_vectors_reference_commands_and_execute(
    golden_fixture: dict[str, Any],
) -> None:
    steps_by_command = {step["command"]["command_id"]: step for step in golden_fixture["steps"]}

    for vector in golden_fixture["determinism_tests"]["command_retries"]:
        command_ref = vector["command_ref"]
        assert command_ref in steps_by_command
        step = steps_by_command[command_ref]
        original = copy.deepcopy(step["command"])
        registry = IdempotencyRegistry()
        first = registry.record(
            original,
            event_count=len(step["expected_events"]),
            journal_count=sum(
                event["event_type"].endswith("JournalPosted") for event in step["expected_events"]
            ),
        )

        candidate = copy.deepcopy(original)
        mutation = vector["mutation"]
        if isinstance(mutation, dict):
            for path, value in mutation.items():
                _set_path(candidate, path, value)

        if vector["expected_result"] == "return_original_result":
            assert registry.record(candidate, event_count=999, journal_count=999) is first
        else:
            assert vector["expected_result"] == "CommandIdConflict"
            with pytest.raises(CommandIdConflict):
                registry.record(candidate, event_count=0, journal_count=0)


def test_missing_retry_command_is_rejected_by_test_contract(
    golden_fixture: dict[str, Any],
) -> None:
    command_ids = {step["command"]["command_id"] for step in golden_fixture["steps"]}
    assert "missing-command" not in command_ids
