"""Canonical command fingerprints and in-memory idempotency semantics."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


class CommandIdConflict(ValueError):
    pass


def canonical_request(command: Mapping[str, Any]) -> bytes:
    semantic_request = {key: value for key, value in command.items() if key != "command_id"}
    return json.dumps(
        semantic_request,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def request_fingerprint(command: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_request(command)).hexdigest()


@dataclass(frozen=True, slots=True)
class CommandResult:
    fingerprint: str
    event_count: int
    journal_count: int


class IdempotencyRegistry:
    def __init__(self) -> None:
        self._results: dict[str, CommandResult] = {}

    def record(
        self,
        command: Mapping[str, Any],
        *,
        event_count: int,
        journal_count: int,
    ) -> CommandResult:
        command_id = str(command["command_id"])
        fingerprint = request_fingerprint(command)
        existing = self._results.get(command_id)
        if existing is not None:
            if existing.fingerprint != fingerprint:
                raise CommandIdConflict(command_id)
            return existing

        result = CommandResult(
            fingerprint=fingerprint,
            event_count=event_count,
            journal_count=journal_count,
        )
        self._results[command_id] = result
        return result
