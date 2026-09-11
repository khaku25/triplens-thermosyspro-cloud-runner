from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from opcua_common import (  # noqa: E402
    AccessEvidence,
    BoundNode,
    DataSample,
    NodeAccessError,
    NodeBindingError,
    NodeContract,
    Quality,
    assert_write_allowed,
    assert_write_role_allowed,
    audit_access,
    bind_nodes,
    read_access_evidence,
    sample_from_datavalue,
)


MODEL_URI = "urn:triplens:openmodelica:model"


class FakeQualifiedName:
    def __init__(self, namespace_index: int, name: str):
        self.NamespaceIndex = namespace_index
        self.Name = name


class FakeNode:
    def __init__(
        self,
        node_id: str,
        namespace_index: int,
        browse_name: str,
        *,
        children=(),
        access=1,
        user_access=1,
    ):
        self.nodeid = node_id
        self._browse_name = FakeQualifiedName(namespace_index, browse_name)
        self._children = list(children)
        self._access = access
        self._user_access = user_access

    def get_browse_name(self):
        return self._browse_name

    def get_children(self):
        return list(self._children)

    def get_access_level(self):
        return self._access

    def get_user_access_level(self):
        return self._user_access


class FakeClient:
    def __init__(self, namespaces, root):
        self._namespaces = namespaces
        self._root = root

    def get_namespace_array(self):
        return list(self._namespaces)

    def get_objects_node(self):
        return self._root


class FakeStatus:
    def __init__(self, value: int, name: str):
        self.value = value
        self.name = name

    def is_bad(self):
        return bool(self.value & 0x80000000)

    def is_uncertain(self):
        return (self.value & 0xC0000000) == 0x40000000


class FakeVariant:
    def __init__(self, value):
        self.Value = value


class FakeDataValue:
    def __init__(self, value, status, source_timestamp, server_timestamp):
        self.Value = FakeVariant(value)
        self.StatusCode = status
        self.SourceTimestamp = source_timestamp
        self.ServerTimestamp = server_timestamp


def contract(
    tag: str,
    name: str,
    *,
    direction: str = "READ",
    uri: str = MODEL_URI,
    stale_after_s: float = 1.0,
) -> NodeContract:
    return NodeContract(
        canonical_tag=tag,
        namespace_uri=uri,
        browse_name=name,
        direction=direction,
        data_type="Double",
        stale_after_s=stale_after_s,
        write_roles=("ECMS_COMMAND",) if direction == "WRITE" else (),
    )


class OPCUACommonContractTests(unittest.TestCase):
    def test_binding_uses_namespace_uri_and_browse_name(self) -> None:
        other = FakeNode("ns=1;i=1", 1, "Speed")
        target = FakeNode("ns=2;i=9", 2, "Speed")
        nested = FakeNode("ns=2;i=2", 2, "Plant", children=(target,))
        root = FakeNode("ns=0;i=85", 0, "Objects", children=(other, nested))
        client = FakeClient(
            ("http://opcfoundation.org/UA/", "urn:other", MODEL_URI), root
        )

        result = bind_nodes(client, (contract("TSP.SPEED", "Speed"),))

        self.assertIs(result["TSP.SPEED"].node, target)
        self.assertEqual(result["TSP.SPEED"].namespace_index, 2)
        self.assertEqual(result["TSP.SPEED"].node_id, "ns=2;i=9")

    def test_rebind_survives_namespace_index_and_nodeid_change(self) -> None:
        first = FakeNode("ns=2;i=9", 2, "Speed")
        second = FakeNode("ns=1;i=407", 1, "Speed")
        first_client = FakeClient(
            ("http://opcfoundation.org/UA/", "urn:other", MODEL_URI),
            FakeNode("ns=0;i=85", 0, "Objects", children=(first,)),
        )
        second_client = FakeClient(
            ("http://opcfoundation.org/UA/", MODEL_URI, "urn:other"),
            FakeNode("ns=0;i=85", 0, "Objects", children=(second,)),
        )
        item = contract("TSP.SPEED", "Speed")

        before = bind_nodes(first_client, (item,))["TSP.SPEED"]
        after = bind_nodes(second_client, (item,))["TSP.SPEED"]

        self.assertEqual((before.namespace_index, after.namespace_index), (2, 1))
        self.assertNotEqual(before.node_id, after.node_id)
        self.assertIs(after.node, second)

    def test_missing_and_ambiguous_exact_identity_fail_closed(self) -> None:
        duplicate_a = FakeNode("ns=1;i=1", 1, "Speed")
        duplicate_b = FakeNode("ns=1;i=2", 1, "Speed")
        client = FakeClient(
            ("http://opcfoundation.org/UA/", MODEL_URI),
            FakeNode(
                "ns=0;i=85", 0, "Objects", children=(duplicate_a, duplicate_b)
            ),
        )
        with self.assertRaises(NodeBindingError):
            bind_nodes(client, (contract("TSP.SPEED", "Speed"),))
        with self.assertRaises(NodeBindingError):
            bind_nodes(client, (contract("TSP.FLOW", "Flow"),))

    def test_datavalue_preserves_all_four_fields(self) -> None:
        received = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)
        source = received - timedelta(milliseconds=30)
        server = received - timedelta(milliseconds=10)
        status = FakeStatus(0, "Good")
        data_value = FakeDataValue(123.5, status, source, server)

        sample = sample_from_datavalue(
            contract("TSP.FLOW", "Flow"),
            data_value,
            received_timestamp=received,
        )

        self.assertIsInstance(sample, DataSample)
        self.assertEqual(sample.value, 123.5)
        self.assertEqual(sample.status_code, 0)
        self.assertEqual(sample.status_name, "Good")
        self.assertIs(sample.source_timestamp, source)
        self.assertIs(sample.server_timestamp, server)
        self.assertIs(sample.received_timestamp, received)
        self.assertEqual(sample.quality, Quality.GOOD)

    def test_quality_precedence_covers_uncertain_bad_stale_missing(self) -> None:
        received = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)
        fresh = received - timedelta(milliseconds=10)
        stale = received - timedelta(seconds=2)
        item = contract("TSP.FLOW", "Flow", stale_after_s=1.0)

        cases = (
            (FakeDataValue(1.0, FakeStatus(0, "Good"), fresh, fresh), Quality.GOOD),
            (
                FakeDataValue(
                    1.0, FakeStatus(0x40000000, "Uncertain"), fresh, fresh
                ),
                Quality.UNCERTAIN,
            ),
            (
                FakeDataValue(1.0, FakeStatus(0x80000000, "Bad"), fresh, fresh),
                Quality.BAD,
            ),
            (
                FakeDataValue(
                    None, FakeStatus(0x803A0000, "BadNotConnected"), fresh, fresh
                ),
                Quality.BAD,
            ),
            (FakeDataValue(1.0, FakeStatus(0, "Good"), stale, stale), Quality.STALE),
            (None, Quality.MISSING),
            (FakeDataValue(None, FakeStatus(0, "Good"), fresh, fresh), Quality.MISSING),
        )
        for data_value, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(
                    sample_from_datavalue(
                        item, data_value, received_timestamp=received
                    ).quality,
                    expected,
                )

    def test_missing_timestamps_are_preserved_not_fabricated(self) -> None:
        received = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)
        sample = sample_from_datavalue(
            contract("TSP.FLOW", "Flow"),
            FakeDataValue(1.0, FakeStatus(0, "Good"), None, None),
            received_timestamp=received,
        )
        self.assertIsNone(sample.source_timestamp)
        self.assertIsNone(sample.server_timestamp)
        self.assertEqual(sample.quality, Quality.GOOD)

    def test_access_audit_and_write_allowlist_fail_closed(self) -> None:
        writable = FakeNode(
            "ns=1;i=10", 1, "Trip", access=3, user_access=3
        )
        readonly = FakeNode(
            "ns=1;i=11", 1, "Speed", access=1, user_access=1
        )
        write_bound = BoundNode(
            contract("CMD.TRIP", "Trip", direction="WRITE"), writable, 1, "ns=1;i=10"
        )
        read_bound = BoundNode(
            contract("TSP.SPEED", "Speed"), readonly, 1, "ns=1;i=11"
        )

        audit_access({"CMD.TRIP": write_bound, "TSP.SPEED": read_bound})
        assert_write_allowed(write_bound, "ECMS_COMMAND")
        assert_write_role_allowed(write_bound, "ECMS_COMMAND")
        with self.assertRaises(NodeAccessError):
            assert_write_allowed(write_bound, "ECMS_VIEWER")
        with self.assertRaises(NodeAccessError):
            assert_write_role_allowed(write_bound, "ECMS_VIEWER")
        with self.assertRaises(NodeAccessError):
            assert_write_allowed(read_bound, "ECMS_COMMAND")
        with self.assertRaises(NodeAccessError):
            assert_write_role_allowed(read_bound, "ECMS_COMMAND")

        exposed_read = BoundNode(
            contract("TSP.SPEED", "Speed"),
            FakeNode("ns=1;i=12", 1, "Speed", access=3, user_access=3),
            1,
            "ns=1;i=12",
        )
        with self.assertRaises(NodeAccessError):
            audit_access({"TSP.SPEED": exposed_read})

    def test_advertised_access_is_preserved_as_evidence(self) -> None:
        node = FakeNode(
            "ns=1;i=10", 1, "Trip", access=1, user_access=1
        )
        bound = BoundNode(
            contract("CMD.TRIP", "Trip", direction="WRITE"),
            node,
            1,
            "ns=1;i=10",
        )

        evidence = read_access_evidence(bound)

        self.assertIsInstance(evidence, AccessEvidence)
        self.assertEqual(evidence.access_level, "1")
        self.assertEqual(evidence.user_access_level, "1")
        self.assertFalse(evidence.current_write_advertised)
        self.assertFalse(evidence.user_current_write_advertised)
        # Application authorization stays fail closed even when advertised
        # access is treated as metadata rather than a service result.
        assert_write_role_allowed(bound, "ECMS_COMMAND")
        with self.assertRaises(NodeAccessError):
            assert_write_role_allowed(bound, "ECMS_VIEWER")


if __name__ == "__main__":
    unittest.main()
