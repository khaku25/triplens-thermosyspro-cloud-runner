from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from native_ecms_opcua_client import (  # noqa: E402
    COMMAND_NODES,
    EVENT_SPECS,
    batch_read_model_samples,
    build_native_events,
    datavalue_rows,
    discover_model_namespace_uri,
    model_node_contracts,
    require_trusted_model_samples,
    resolve_ll_trip_requests,
)
from opcua_common import BoundNode, DataSample, NodeContract, Quality  # noqa: E402


MODEL_URI = "urn:openmodelica:test-model"


class FakeQualifiedName:
    def __init__(self, namespace_index: int, name: str):
        self.NamespaceIndex = namespace_index
        self.Name = name


class FakeNode:
    def __init__(self, nodeid: str, namespace_index: int, name: str, children=()):
        self.nodeid = nodeid
        self._browse_name = FakeQualifiedName(namespace_index, name)
        self._children = list(children)

    def get_browse_name(self):
        return self._browse_name

    def get_children(self):
        return list(self._children)


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
    def __init__(self, value, status, source, server):
        self.Value = FakeVariant(value)
        self.StatusCode = status
        self.SourceTimestamp = source
        self.ServerTimestamp = server


class FakeUaClient:
    def __init__(self, values):
        self.values = list(values)
        self.calls = []

    def get_attributes(self, nodeids, attribute):
        self.calls.append((list(nodeids), attribute))
        return list(self.values)


class FakeClient:
    def __init__(self, namespaces, root, values=()):
        self._namespaces = list(namespaces)
        self._root = root
        self.uaclient = FakeUaClient(values)

    def get_namespace_array(self):
        return list(self._namespaces)

    def get_objects_node(self):
        return self._root


class FakeUa:
    class AttributeIds:
        Value = 13


def contract(tag: str, name: str, direction: str = "READ") -> NodeContract:
    return NodeContract(
        canonical_tag=tag,
        namespace_uri=MODEL_URI,
        browse_name=name,
        direction=direction,
        data_type="Double",
        stale_after_s=5.0,
        write_roles=("ECMS_COMMAND",) if direction == "WRITE" else (),
    )


def sample(
    tag: str,
    value: float,
    source: datetime | None,
    *,
    quality: Quality = Quality.GOOD,
) -> DataSample:
    received = datetime(2026, 9, 11, 12, 0, 1, tzinfo=timezone.utc)
    return DataSample(
        canonical_tag=tag,
        value=value,
        status_code=0,
        status_name="Good",
        source_timestamp=source,
        server_timestamp=source,
        received_timestamp=received,
        quality=quality,
    )


class NativeOPCUADataValueTests(unittest.TestCase):
    def test_model_namespace_discovery_requires_one_complete_uri(self) -> None:
        root = FakeNode(
            "ns=0;i=85",
            0,
            "Objects",
            children=(
                FakeNode("ns=1;i=1", 1, "Trip"),
                FakeNode("ns=2;i=1", 2, "Trip"),
                FakeNode("ns=2;i=2", 2, "Speed"),
            ),
        )
        client = FakeClient(
            ("http://opcfoundation.org/UA/", "urn:partial", MODEL_URI), root
        )
        self.assertEqual(
            discover_model_namespace_uri(client, {"Trip", "Speed"}), MODEL_URI
        )

    def test_batch_read_keeps_full_datavalue_and_writes_evidence_rows(self) -> None:
        now = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)
        node = FakeNode("ns=2;i=41", 2, "Speed")
        bound = BoundNode(contract("speed", "Speed"), node, 2, str(node.nodeid))
        client = FakeClient(
            ("http://opcfoundation.org/UA/", "urn:other", MODEL_URI),
            FakeNode("ns=0;i=85", 0, "Objects"),
            (FakeDataValue(1234.5, FakeStatus(0, "Good"), now, now),),
        )

        samples = batch_read_model_samples(
            client, {"speed": bound}, FakeUa, received_timestamp=now
        )

        self.assertEqual(client.uaclient.calls, [([node.nodeid], 13)])
        self.assertEqual(samples["speed"].value, 1234.5)
        self.assertEqual(samples["speed"].status_name, "Good")
        self.assertIs(samples["speed"].source_timestamp, now)
        self.assertIs(samples["speed"].server_timestamp, now)
        evidence = datavalue_rows(7, 2.5, {"speed": bound}, samples)[0]
        self.assertEqual(evidence["evidence_kind"], "MODEL_FEEDBACK")
        self.assertEqual(evidence["namespace_uri"], MODEL_URI)
        self.assertEqual(evidence["node_id"], "ns=2;i=41")

    def test_fail_closed_on_quality_or_missing_required_source_time(self) -> None:
        now = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)
        for bad_sample in (
            sample("speed", 1.0, now, quality=Quality.UNCERTAIN),
            sample("speed", 1.0, now, quality=Quality.BAD),
            sample("speed", 1.0, now, quality=Quality.STALE),
            sample("speed", 1.0, now, quality=Quality.MISSING),
            sample("speed", 1.0, None),
        ):
            with self.subTest(quality=bad_sample.quality, source=bad_sample.source_timestamp):
                with self.assertRaises(ValueError):
                    require_trusted_model_samples({"speed": bad_sample})

    def test_event_uses_datavalue_timestamps_quality_and_write_echo_label(self) -> None:
        previous = {}
        current = {}
        for spec in EVENT_SPECS:
            stable = spec.threshold + 1.0 if spec.edge in ("FALL", "LOW") else 0.0
            previous[spec.field] = stable
            current[spec.field] = stable
        previous.update(time_s=1.0, common_st_trip_request=0)
        current.update(time_s=2.0, common_st_trip_request=1)
        source = datetime(2026, 9, 11, 12, 0, 0, 123000, tzinfo=timezone.utc)
        received = source + timedelta(milliseconds=17)
        evidence = sample("common_st_trip_request", 1.0, source)
        evidence = DataSample(
            **{**evidence.__dict__, "received_timestamp": received}
        )

        events = build_native_events(
            [previous, current], 1.5, [{}, {"common_st_trip_request": evidence}]
        )

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["canonical_tag"], "COMMON.ST_TRIP.REQUEST")
        self.assertEqual(event["source_time_ms"], round(source.timestamp() * 1000))
        self.assertEqual(event["event_time_ms"], round(received.timestamp() * 1000))
        self.assertEqual(event["quality"], "GOOD")
        self.assertEqual(event["provenance"], "LIVE_OPC_UA_WRITE_ECHO_DATAVALUE")

    def test_st_request_has_an_independent_writable_model_boundary(self) -> None:
        self.assertEqual(
            COMMAND_NODES["common_st_trip_request"],
            "vppExternalSTTripCommandNative",
        )
        contracts = {item.canonical_tag: item for item in model_node_contracts(MODEL_URI)}
        self.assertEqual(contracts["common_st_trip_request"].direction, "WRITE")
        self.assertEqual(
            contracts["common_st_trip_request"].browse_name,
            "vppExternalSTTripCommandNative",
        )
        self.assertNotEqual(
            contracts["common_st_trip_request"].browse_name,
            contracts["gt_trip_command_readback"].browse_name,
        )
        self.assertEqual(resolve_ll_trip_requests(True, True, False), (True, False))
        self.assertEqual(resolve_ll_trip_requests(True, False, True), (False, True))


if __name__ == "__main__":
    unittest.main()
