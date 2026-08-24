"""Canonical typed-command fingerprints and in-memory idempotency semantics."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from ledger_sim.domain.commands import Command, command_primitive
from ledger_sim.domain.values import DomainId


class CommandIdConflict(ValueError):
    pass


def canonical_request(command: Command) -> bytes:
    semantic_request = command_primitive(command)
    del semantic_request["command_id"]
    return json.dumps(
        semantic_request,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def request_fingerprint(command: Command) -> str:
    return hashlib.sha256(canonical_request(command)).hexdigest()


@dataclass(frozen=True, slots=True)
class RegisteredResult[ResultT]:
    fingerprint: str
    result: ResultT


class IdempotencyRegistry[ResultT]:
    def __init__(self) -> None:
        self._results: dict[DomainId, RegisteredResult[ResultT]] = {}

    def find(self, command: Command) -> ResultT | None:
        fingerprint = request_fingerprint(command)
        existing = self._results.get(command.command_id)
        if existing is None:
            return None
        if existing.fingerprint != fingerprint:
            raise CommandIdConflict(str(command.command_id))
        return existing.result

    def register(self, command: Command, result: ResultT) -> None:
        if command.command_id in self._results:
            raise RuntimeError("command result was already registered")
        self._results[command.command_id] = RegisteredResult(
            request_fingerprint(command),
            result,
        )
