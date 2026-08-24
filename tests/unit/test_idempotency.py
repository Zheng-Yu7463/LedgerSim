from __future__ import annotations

import copy
from typing import Any

import pytest

from ledger_sim.domain.commands import command_primitive, parse_command
from ledger_sim.domain.idempotency import (
    CommandIdConflict,
    IdempotencyRegistry,
    request_fingerprint,
)


def test_typed_command_fingerprint_covers_all_semantic_fields(
    golden_fixture: dict[str, Any],
) -> None:
    raw = copy.deepcopy(golden_fixture["steps"][0]["command"])
    command = parse_command(raw)
    primitive = command_primitive(command)
    assert primitive["payload"]["fixed_consideration"] == "6000.00"
    assert primitive["requested_at"] == "2026-03-01T01:00:00.000000Z"

    changed = copy.deepcopy(raw)
    changed["payload"]["fixed_consideration"] = "6000.01"
    assert request_fingerprint(parse_command(changed)) != request_fingerprint(command)


def test_registry_returns_original_result_and_rejects_conflict(
    golden_fixture: dict[str, Any],
) -> None:
    raw = copy.deepcopy(golden_fixture["steps"][0]["command"])
    command = parse_command(raw)
    result = object()
    registry: IdempotencyRegistry[object] = IdempotencyRegistry()
    assert registry.find(command) is None
    registry.register(command, result)
    assert registry.find(command) is result

    raw["requested_at"] = "2026-03-01T01:00:01.000000Z"
    with pytest.raises(CommandIdConflict):
        registry.find(parse_command(raw))
