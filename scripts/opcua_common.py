#!/usr/bin/env python3
"""Reusable OPC UA address, DataValue, quality, and access contracts.

This module deliberately has no import-time dependency on ``python-opcua``.
The production client can pass real python-opcua Client, Node, and DataValue
objects, while unit tests can use small duck-typed fakes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Mapping


CURRENT_READ = 0x01
CURRENT_WRITE = 0x02


class Quality(str, Enum):
    GOOD = "GOOD"
    UNCERTAIN = "UNCERTAIN"
    BAD = "BAD"
    STALE = "STALE"
    MISSING = "MISSING"


class NodeBindingError(ValueError):
    """The live address space does not satisfy the declared node contract."""


class NodeAccessError(PermissionError):
    """An application write violates the declared or live OPC UA access rules."""


@dataclass(frozen=True)
class NodeContract:
    canonical_tag: str
    namespace_uri: str
    browse_name: str
    direction: str
    data_type: str
    stale_after_s: float
    required: bool = True
    write_roles: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        direction = self.direction.upper()
        if direction not in {"READ", "WRITE"}:
            raise ValueError(f"unsupported OPC UA direction: {self.direction}")
        if not self.namespace_uri or not self.browse_name:
            raise ValueError("OPC UA nodes require namespace_uri and browse_name")
        if self.stale_after_s < 0:
            raise ValueError("stale_after_s must be non-negative")
        if direction == "WRITE" and not self.write_roles:
            raise ValueError("WRITE node contracts require at least one write role")
        if direction == "READ" and self.write_roles:
            raise ValueError("READ node contracts cannot grant write roles")
        object.__setattr__(self, "direction", direction)


@dataclass(frozen=True)
class BoundNode:
    contract: NodeContract
    node: Any
    namespace_index: int
    node_id: str


@dataclass(frozen=True)
class DataSample:
    """A value plus the complete OPC UA DataValue evidence used to trust it."""

    canonical_tag: str
    value: Any
    status_code: int | None
    status_name: str | None
    source_timestamp: datetime | None
    server_timestamp: datetime | None
    received_timestamp: datetime
    quality: Quality


def _qualified_name(node: Any) -> tuple[int, str]:
    browse_name = node.get_browse_name()
    namespace_index = int(getattr(browse_name, "NamespaceIndex"))
    name = str(getattr(browse_name, "Name"))
    return namespace_index, name


def _node_id_text(node: Any) -> str:
    node_id = getattr(node, "nodeid", None)
    return str(node_id if node_id is not None else node)


def _walk_nodes(root: Any) -> Iterable[Any]:
    """Walk an OPC UA hierarchy without importing the OPC UA SDK."""

    pending = list(root.get_children())
    visited: set[str] = set()
    while pending:
        node = pending.pop(0)
        identity = _node_id_text(node)
        if identity in visited:
            continue
        visited.add(identity)
        yield node
        try:
            pending.extend(node.get_children())
        except Exception:
            # Variable nodes commonly reject or return no hierarchical children.
            continue


def bind_nodes(
    client: Any,
    contracts: Iterable[NodeContract],
    *,
    root: Any | None = None,
) -> dict[str, BoundNode]:
    """Resolve nodes by stable ``(Namespace URI, BrowseName)`` identity.

    Namespace indexes and numeric NodeIds are session-local implementation
    details.  Calling this function after every reconnect intentionally
    re-reads the NamespaceArray and rebuilds all bindings.
    """

    contracts = tuple(contracts)
    namespace_array = tuple(client.get_namespace_array())
    address_space: dict[tuple[str, str], list[tuple[Any, int]]] = {}
    for node in _walk_nodes(root or client.get_objects_node()):
        try:
            namespace_index, browse_name = _qualified_name(node)
        except Exception:
            continue
        if not 0 <= namespace_index < len(namespace_array):
            raise NodeBindingError(
                f"node {browse_name} has unknown namespace index {namespace_index}"
            )
        key = (str(namespace_array[namespace_index]), browse_name)
        address_space.setdefault(key, []).append((node, namespace_index))

    bound: dict[str, BoundNode] = {}
    for contract in contracts:
        matches = address_space.get(
            (contract.namespace_uri, contract.browse_name), []
        )
        if not matches:
            if contract.required:
                raise NodeBindingError(
                    "required OPC UA node missing: "
                    f"{contract.namespace_uri}::{contract.browse_name}"
                )
            continue
        if len(matches) != 1:
            raise NodeBindingError(
                "ambiguous OPC UA node identity: "
                f"{contract.namespace_uri}::{contract.browse_name}"
            )
        node, namespace_index = matches[0]
        if contract.canonical_tag in bound:
            raise NodeBindingError(
                f"duplicate canonical tag contract: {contract.canonical_tag}"
            )
        bound[contract.canonical_tag] = BoundNode(
            contract=contract,
            node=node,
            namespace_index=namespace_index,
            node_id=_node_id_text(node),
        )
    return bound


def _status_value(status: Any) -> int | None:
    if status is None:
        return None
    value = getattr(status, "value", status)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _status_name(status: Any) -> str | None:
    if status is None:
        return None
    name = getattr(status, "name", None)
    if name is not None:
        return str(name)
    return str(status)


def _status_quality(status: Any) -> Quality:
    if status is None:
        return Quality.MISSING
    for method_name, quality in (
        ("is_bad", Quality.BAD),
        ("is_uncertain", Quality.UNCERTAIN),
    ):
        method = getattr(status, method_name, None)
        if callable(method) and bool(method()):
            return quality
    value = _status_value(status)
    if value is None:
        return Quality.MISSING
    severity = value & 0xC0000000
    if severity & 0x80000000:
        return Quality.BAD
    if severity == 0x40000000:
        return Quality.UNCERTAIN
    return Quality.GOOD


def _variant_value(data_value: Any) -> tuple[bool, Any]:
    if data_value is None:
        return False, None
    variant = getattr(data_value, "Value", None)
    if variant is None or not hasattr(variant, "Value"):
        return False, None
    value = variant.Value
    return value is not None, value


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def sample_from_datavalue(
    contract: NodeContract,
    data_value: Any,
    *,
    received_timestamp: datetime | None = None,
) -> DataSample:
    """Preserve a DataValue and assign deterministic application quality.

    A missing service result is MISSING.  For a returned DataValue, its BAD or
    UNCERTAIN StatusCode takes precedence over an absent payload; a Good value
    without a payload is MISSING.  Staleness uses SourceTimestamp when present
    and falls back to ServerTimestamp.  Missing timestamps are preserved as
    null; they are not fabricated.
    """

    received = received_timestamp or datetime.now(timezone.utc)
    received_utc = _as_utc(received)
    present, value = _variant_value(data_value)
    status = getattr(data_value, "StatusCode", None) if data_value is not None else None
    source_timestamp = (
        getattr(data_value, "SourceTimestamp", None)
        if data_value is not None else None
    )
    server_timestamp = (
        getattr(data_value, "ServerTimestamp", None)
        if data_value is not None else None
    )

    quality = (
        Quality.MISSING if data_value is None else _status_quality(status)
    )
    if quality == Quality.GOOD and not present:
        quality = Quality.MISSING
    timestamp = source_timestamp or server_timestamp
    if quality == Quality.GOOD and timestamp is not None:
        age_s = (received_utc - _as_utc(timestamp)).total_seconds()
        if age_s > contract.stale_after_s:
            quality = Quality.STALE

    return DataSample(
        canonical_tag=contract.canonical_tag,
        value=value,
        status_code=_status_value(status),
        status_name=_status_name(status),
        source_timestamp=source_timestamp,
        server_timestamp=server_timestamp,
        received_timestamp=received,
        quality=quality,
    )


def _has_access(access: Any, mask: int, enum_name: str) -> bool:
    if isinstance(access, int):
        return bool(access & mask)
    try:
        values = tuple(access)
    except TypeError:
        return False
    for value in values:
        name = getattr(value, "name", str(value).rsplit(".", 1)[-1])
        if str(name) == enum_name:
            return True
        try:
            if int(getattr(value, "value", value)) == mask:
                return True
        except (TypeError, ValueError):
            continue
    return False


def audit_access(bound_nodes: Mapping[str, BoundNode]) -> None:
    """Fail if live node access contradicts the READ/WRITE contract."""

    for bound in bound_nodes.values():
        access = bound.node.get_access_level()
        user_access = bound.node.get_user_access_level()
        server_write = _has_access(access, CURRENT_WRITE, "CurrentWrite")
        user_write = _has_access(user_access, CURRENT_WRITE, "CurrentWrite")
        if bound.contract.direction == "WRITE":
            if not server_write or not user_write:
                raise NodeAccessError(
                    f"contract WRITE is not writable: {bound.contract.canonical_tag}"
                )
        elif server_write or user_write:
            raise NodeAccessError(
                f"contract READ is exposed writable: {bound.contract.canonical_tag}"
            )


def assert_write_allowed(bound: BoundNode, role: str) -> None:
    """Enforce both the application allowlist and live OPC UA access bits."""

    contract = bound.contract
    if contract.direction != "WRITE":
        raise NodeAccessError(f"write denied for READ node: {contract.canonical_tag}")
    if role not in contract.write_roles:
        raise NodeAccessError(
            f"role {role!r} cannot write {contract.canonical_tag}"
        )
    if not _has_access(
        bound.node.get_access_level(), CURRENT_WRITE, "CurrentWrite"
    ) or not _has_access(
        bound.node.get_user_access_level(), CURRENT_WRITE, "CurrentWrite"
    ):
        raise NodeAccessError(
            f"live OPC UA access denies write: {contract.canonical_tag}"
        )
