#!/usr/bin/env python3
"""Fail-closed command transaction contract for ECMS OPC UA commands.

The core deliberately does not perform OPC UA I/O or equipment actuation.  A
caller first persists the state returned by :meth:`receive`, dispatches only
when the disposition is ``DISPATCH``, and then records the terminal outcome
with :meth:`complete`.  Persisting the journal before dispatch is what makes a
reconnect/replay safe: an in-flight command is never dispatched a second time.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Iterable, Mapping


STATE_VERSION = 1


class Disposition(str, Enum):
    DISPATCH = "DISPATCH"
    REPLAY = "REPLAY"
    REJECT = "REJECT"


class ResultCode(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    REJECTED = "REJECTED"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    TIMEOUT = "TIMEOUT"
    REQUEST_ID_MISMATCH = "REQUEST_ID_MISMATCH"
    DUPLICATE_REQUEST = "DUPLICATE_REQUEST"
    OUT_OF_ORDER = "OUT_OF_ORDER"


TERMINAL_RESULT_CODES = frozenset(
    {
        ResultCode.SUCCESS,
        ResultCode.REJECTED,
        ResultCode.EXECUTION_ERROR,
        ResultCode.TIMEOUT,
        ResultCode.REQUEST_ID_MISMATCH,
        ResultCode.DUPLICATE_REQUEST,
        ResultCode.OUT_OF_ORDER,
    }
)


class TransactionProtocolError(ValueError):
    """A completion or restored checkpoint violates the transaction contract."""


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return _utc(value, "timestamp").isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _parse_timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise TransactionProtocolError(f"invalid {field}: {value!r}") from exc
    try:
        return _utc(parsed, field)
    except ValueError as exc:
        raise TransactionProtocolError(str(exc)) from exc


def _identifier(value: str, field: str, *, uppercase: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    canonical = value.strip()
    if any(ord(character) < 0x20 for character in canonical):
        raise ValueError(f"{field} contains a control character")
    return canonical.upper() if uppercase else canonical


def _json(payload: Mapping[str, Any] | list[Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


@dataclass(frozen=True)
class CommandRequest:
    request_id: str
    equipment_id: str
    command: str
    issued_timestamp: datetime
    source_timestamp: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _identifier(self.request_id, "request_id"))
        object.__setattr__(
            self, "equipment_id", _identifier(self.equipment_id, "equipment_id", uppercase=True)
        )
        object.__setattr__(self, "command", _identifier(self.command, "command", uppercase=True))
        object.__setattr__(
            self, "issued_timestamp", _utc(self.issued_timestamp, "issued_timestamp")
        )
        object.__setattr__(
            self, "source_timestamp", _utc(self.source_timestamp, "source_timestamp")
        )
        if self.source_timestamp < self.issued_timestamp:
            raise ValueError("source_timestamp cannot precede issued_timestamp")

    def to_dict(self) -> dict[str, str]:
        return {
            "command": self.command,
            "equipment_id": self.equipment_id,
            "issued_timestamp": _timestamp(self.issued_timestamp),
            "request_id": self.request_id,
            "source_timestamp": _timestamp(self.source_timestamp),
        }

    def to_json(self) -> str:
        return _json(self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CommandRequest":
        required = {
            "request_id",
            "equipment_id",
            "command",
            "issued_timestamp",
            "source_timestamp",
        }
        missing = required.difference(payload)
        if missing:
            raise TransactionProtocolError(
                "command request missing fields: " + ", ".join(sorted(missing))
            )
        return cls(
            request_id=str(payload["request_id"]),
            equipment_id=str(payload["equipment_id"]),
            command=str(payload["command"]),
            issued_timestamp=_parse_timestamp(
                str(payload["issued_timestamp"]), "issued_timestamp"
            ),
            source_timestamp=_parse_timestamp(
                str(payload["source_timestamp"]), "source_timestamp"
            ),
        )

    @property
    def request_digest(self) -> str:
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    @property
    def command_fingerprint(self) -> str:
        # Deliberately excludes request_id so two IDs cannot execute the same
        # command occurrence twice.
        payload = self.to_dict()
        del payload["request_id"]
        return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CommandResult:
    request_id: str
    equipment_id: str
    command: str
    issued_timestamp: datetime
    source_timestamp: datetime
    ack_id: str
    result_code: ResultCode
    detail: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _identifier(self.request_id, "request_id"))
        object.__setattr__(
            self, "equipment_id", _identifier(self.equipment_id, "equipment_id", uppercase=True)
        )
        object.__setattr__(self, "command", _identifier(self.command, "command", uppercase=True))
        object.__setattr__(self, "ack_id", _identifier(self.ack_id, "ack_id"))
        object.__setattr__(
            self, "issued_timestamp", _utc(self.issued_timestamp, "issued_timestamp")
        )
        object.__setattr__(
            self, "source_timestamp", _utc(self.source_timestamp, "source_timestamp")
        )
        if not isinstance(self.result_code, ResultCode):
            object.__setattr__(self, "result_code", ResultCode(self.result_code))

    @property
    def is_terminal(self) -> bool:
        return self.result_code in TERMINAL_RESULT_CODES

    def to_dict(self) -> dict[str, str]:
        return {
            "ack_id": self.ack_id,
            "command": self.command,
            "detail": self.detail,
            "equipment_id": self.equipment_id,
            "issued_timestamp": _timestamp(self.issued_timestamp),
            "request_id": self.request_id,
            "result_code": self.result_code.value,
            "source_timestamp": _timestamp(self.source_timestamp),
        }

    def to_json(self) -> str:
        """Canonical JSON safe to store in a String scalar or event field."""

        return _json(self.to_dict())

    def to_scalar_map(self, prefix: str = "") -> dict[str, str]:
        """Return only OPC UA scalar-compatible strings with stable keys."""

        return {f"{prefix}{key}": value for key, value in self.to_dict().items()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CommandResult":
        required = {
            "request_id",
            "equipment_id",
            "command",
            "issued_timestamp",
            "source_timestamp",
            "ack_id",
            "result_code",
        }
        missing = required.difference(payload)
        if missing:
            raise TransactionProtocolError(
                "command result missing fields: " + ", ".join(sorted(missing))
            )
        try:
            result_code = ResultCode(str(payload["result_code"]))
        except ValueError as exc:
            raise TransactionProtocolError(
                f"unknown result_code: {payload['result_code']!r}"
            ) from exc
        return cls(
            request_id=str(payload["request_id"]),
            equipment_id=str(payload["equipment_id"]),
            command=str(payload["command"]),
            issued_timestamp=_parse_timestamp(
                str(payload["issued_timestamp"]), "issued_timestamp"
            ),
            source_timestamp=_parse_timestamp(
                str(payload["source_timestamp"]), "source_timestamp"
            ),
            ack_id=str(payload["ack_id"]),
            result_code=result_code,
            detail=str(payload.get("detail", "")),
        )


@dataclass(frozen=True)
class Receipt:
    disposition: Disposition
    result: CommandResult

    @property
    def should_dispatch(self) -> bool:
        return self.disposition is Disposition.DISPATCH


@dataclass(frozen=True)
class _Record:
    request: CommandRequest
    result: CommandResult
    was_dispatched: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request.to_dict(),
            "result": self.result.to_dict(),
            "was_dispatched": self.was_dispatched,
        }


def _ack_id(request: CommandRequest) -> str:
    return "ACK-" + request.request_digest[:24].upper()


def _result(
    request: CommandRequest,
    result_code: ResultCode,
    source_timestamp: datetime,
    detail: str = "",
) -> CommandResult:
    return CommandResult(
        request_id=request.request_id,
        equipment_id=request.equipment_id,
        command=request.command,
        issued_timestamp=request.issued_timestamp,
        source_timestamp=source_timestamp,
        ack_id=_ack_id(request),
        result_code=result_code,
        detail=detail,
    )


class CommandTransactionCore:
    """In-memory journal with deterministic persistence and replay behavior."""

    def __init__(self, timeout: timedelta = timedelta(seconds=2)) -> None:
        if timeout < timedelta(milliseconds=1):
            raise ValueError("timeout must be at least one millisecond")
        self.timeout = timeout
        self._records: dict[str, _Record] = {}
        self._conflicts: dict[str, tuple[CommandRequest, CommandResult]] = {}

    def receive(self, request: CommandRequest, *, received_at: datetime) -> Receipt:
        now = _utc(received_at, "received_at")
        existing = self._records.get(request.request_id)
        if existing is not None:
            if existing.request == request:
                return Receipt(Disposition.REPLAY, existing.result)
            conflict_key = request.request_digest
            conflict = self._conflicts.get(conflict_key)
            if conflict is None:
                result = _result(
                    request,
                    ResultCode.REQUEST_ID_MISMATCH,
                    now,
                    "request_id already belongs to different immutable command fields",
                )
                self._conflicts[conflict_key] = (request, result)
            else:
                _, result = conflict
            return Receipt(Disposition.REJECT, result)

        fingerprint_owner = next(
            (
                record
                for record in self._records.values()
                if record.was_dispatched
                and record.request.command_fingerprint == request.command_fingerprint
            ),
            None,
        )
        if fingerprint_owner is not None:
            return self._reject_and_remember(
                request,
                ResultCode.DUPLICATE_REQUEST,
                now,
                f"same command occurrence already owned by {fingerprint_owner.request.request_id}",
            )

        latest = max(
            (
                record.request.issued_timestamp
                for record in self._records.values()
                if record.was_dispatched
                and record.request.equipment_id == request.equipment_id
            ),
            default=None,
        )
        if latest is not None and request.issued_timestamp <= latest:
            return self._reject_and_remember(
                request,
                ResultCode.OUT_OF_ORDER,
                now,
                "issued_timestamp is not newer than the last dispatched command",
            )

        if now - request.issued_timestamp >= self.timeout:
            return self._reject_and_remember(
                request,
                ResultCode.TIMEOUT,
                now,
                "command expired before dispatch",
            )

        pending = _result(request, ResultCode.PENDING, now, "dispatch journaled")
        self._records[request.request_id] = _Record(
            request=request, result=pending, was_dispatched=True
        )
        return Receipt(Disposition.DISPATCH, pending)

    def _reject_and_remember(
        self,
        request: CommandRequest,
        code: ResultCode,
        source_timestamp: datetime,
        detail: str,
    ) -> Receipt:
        rejected = _result(request, code, source_timestamp, detail)
        self._records[request.request_id] = _Record(
            request=request, result=rejected, was_dispatched=False
        )
        return Receipt(Disposition.REJECT, rejected)

    def complete(
        self,
        *,
        request_id: str,
        ack_id: str,
        result_code: ResultCode,
        source_timestamp: datetime,
        detail: str = "",
    ) -> CommandResult:
        request_id = _identifier(request_id, "request_id")
        ack_id = _identifier(ack_id, "ack_id")
        when = _utc(source_timestamp, "source_timestamp")
        try:
            code = result_code if isinstance(result_code, ResultCode) else ResultCode(result_code)
        except ValueError as exc:
            raise TransactionProtocolError(f"unknown result_code: {result_code!r}") from exc
        if code not in {ResultCode.SUCCESS, ResultCode.REJECTED, ResultCode.EXECUTION_ERROR}:
            raise TransactionProtocolError(
                f"complete requires an executor terminal result, got {code.value}"
            )

        record = self._records.get(request_id)
        if record is None or not record.was_dispatched:
            raise TransactionProtocolError(f"unknown or non-dispatched request_id: {request_id}")
        if ack_id != record.result.ack_id:
            raise TransactionProtocolError(f"ack_id mismatch for request_id {request_id}")
        if when < record.request.source_timestamp:
            raise TransactionProtocolError(
                "completion source_timestamp precedes command source_timestamp"
            )
        if record.result.is_terminal:
            if (
                record.result.result_code == code
                and record.result.source_timestamp == when
                and record.result.detail == detail
            ):
                return record.result
            raise TransactionProtocolError(
                f"conflicting duplicate completion for request_id {request_id}"
            )

        completed = replace(
            record.result,
            result_code=code,
            source_timestamp=when,
            detail=detail,
        )
        self._records[request_id] = replace(record, result=completed)
        return completed

    def expire(self, *, now: datetime) -> tuple[CommandResult, ...]:
        current = _utc(now, "now")
        expired: list[CommandResult] = []
        for request_id in sorted(self._records):
            record = self._records[request_id]
            if (
                record.was_dispatched
                and record.result.result_code is ResultCode.PENDING
                and current - record.request.issued_timestamp >= self.timeout
            ):
                timed_out = replace(
                    record.result,
                    result_code=ResultCode.TIMEOUT,
                    source_timestamp=current,
                    detail="terminal acknowledgement deadline exceeded",
                )
                self._records[request_id] = replace(record, result=timed_out)
                expired.append(timed_out)
        return tuple(expired)

    def get(self, request_id: str) -> CommandResult | None:
        record = self._records.get(request_id)
        return record.result if record is not None else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflicts": [
                {
                    "request": self._conflicts[digest][0].to_dict(),
                    "request_digest": digest,
                    "result": self._conflicts[digest][1].to_dict(),
                }
                for digest in sorted(self._conflicts)
            ],
            "records": [self._records[key].to_dict() for key in sorted(self._records)],
            "state_version": STATE_VERSION,
            "timeout_ms": round(self.timeout.total_seconds() * 1000),
        }

    def to_json(self) -> str:
        """Canonical checkpoint; persist atomically before any actuator write."""

        return _json(self.to_dict())

    @classmethod
    def from_json(cls, payload: str) -> "CommandTransactionCore":
        try:
            state = json.loads(payload)
        except (TypeError, json.JSONDecodeError) as exc:
            raise TransactionProtocolError("invalid command transaction checkpoint JSON") from exc
        if not isinstance(state, dict) or state.get("state_version") != STATE_VERSION:
            raise TransactionProtocolError("unsupported command transaction state_version")
        timeout_ms = state.get("timeout_ms")
        if not isinstance(timeout_ms, int) or timeout_ms <= 0:
            raise TransactionProtocolError("checkpoint timeout_ms must be a positive integer")
        core = cls(timedelta(milliseconds=timeout_ms))
        records = state.get("records")
        conflicts = state.get("conflicts")
        if not isinstance(records, list) or not isinstance(conflicts, list):
            raise TransactionProtocolError("checkpoint records/conflicts must be arrays")

        for payload_record in records:
            if not isinstance(payload_record, dict):
                raise TransactionProtocolError("checkpoint record must be an object")
            try:
                request = CommandRequest.from_dict(payload_record["request"])
                result = CommandResult.from_dict(payload_record["result"])
                was_dispatched = payload_record["was_dispatched"]
            except (KeyError, TypeError, ValueError) as exc:
                raise TransactionProtocolError("malformed checkpoint record") from exc
            if not isinstance(was_dispatched, bool):
                raise TransactionProtocolError("was_dispatched must be boolean")
            core._validate_restored_pair(request, result, was_dispatched)
            if request.request_id in core._records:
                raise TransactionProtocolError("duplicate request_id in checkpoint")
            core._records[request.request_id] = _Record(
                request=request, result=result, was_dispatched=was_dispatched
            )

        dispatched_fingerprints: set[str] = set()
        for record in core._records.values():
            if record.was_dispatched:
                if record.request.command_fingerprint in dispatched_fingerprints:
                    raise TransactionProtocolError(
                        "duplicate dispatched command fingerprint in checkpoint"
                    )
                dispatched_fingerprints.add(record.request.command_fingerprint)

        for payload_conflict in conflicts:
            if not isinstance(payload_conflict, dict):
                raise TransactionProtocolError("checkpoint conflict must be an object")
            digest = payload_conflict.get("request_digest")
            request_payload = payload_conflict.get("request")
            result_payload = payload_conflict.get("result")
            if (
                not isinstance(digest, str)
                or not isinstance(request_payload, dict)
                or not isinstance(result_payload, dict)
            ):
                raise TransactionProtocolError("malformed checkpoint conflict")
            request = CommandRequest.from_dict(request_payload)
            result = CommandResult.from_dict(result_payload)
            core._validate_restored_pair(request, result, False)
            if result.result_code is not ResultCode.REQUEST_ID_MISMATCH:
                raise TransactionProtocolError("conflict must be REQUEST_ID_MISMATCH")
            if digest != request.request_digest:
                raise TransactionProtocolError("conflict request_digest mismatch")
            primary = core._records.get(request.request_id)
            if primary is None or primary.request == request:
                raise TransactionProtocolError(
                    "conflict must reuse an existing request_id with different fields"
                )
            if digest in core._conflicts:
                raise TransactionProtocolError("duplicate conflict digest in checkpoint")
            core._conflicts[digest] = (request, result)
        return core

    @staticmethod
    def _validate_restored_pair(
        request: CommandRequest, result: CommandResult, was_dispatched: bool
    ) -> None:
        if (
            result.request_id != request.request_id
            or result.equipment_id != request.equipment_id
            or result.command != request.command
            or result.issued_timestamp != request.issued_timestamp
            or result.ack_id != _ack_id(request)
        ):
            raise TransactionProtocolError("checkpoint request/result identity mismatch")
        if was_dispatched and result.result_code in {
            ResultCode.DUPLICATE_REQUEST,
            ResultCode.OUT_OF_ORDER,
            ResultCode.REQUEST_ID_MISMATCH,
        }:
            raise TransactionProtocolError("dispatched record has a rejection-only result")
        if not was_dispatched and result.result_code in {
            ResultCode.PENDING,
            ResultCode.SUCCESS,
            ResultCode.EXECUTION_ERROR,
        }:
            raise TransactionProtocolError("non-dispatched record has executor result")


def serialize_results(results: Iterable[CommandResult]) -> str:
    """Canonical JSON array for batched event evidence or OPC UA String nodes."""

    return _json([result.to_dict() for result in results])
