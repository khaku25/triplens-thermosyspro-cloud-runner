from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from command_transaction import (  # noqa: E402
    CommandRequest,
    CommandTransactionCore,
    Disposition,
    ResultCode,
    TransactionProtocolError,
    serialize_results,
)


T0 = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)


def request(
    request_id: str = "REQ-001",
    *,
    equipment: str = "VCB-A02",
    command: str = "TRIP",
    issued: datetime = T0,
    source: datetime | None = None,
) -> CommandRequest:
    return CommandRequest(
        request_id=request_id,
        equipment_id=equipment,
        command=command,
        issued_timestamp=issued,
        source_timestamp=source or issued,
    )


class CommandTransactionTests(unittest.TestCase):
    def test_required_fields_and_timestamps_are_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            request("")
        with self.assertRaises(ValueError):
            request("REQ", equipment=" ")
        with self.assertRaises(ValueError):
            request("REQ", issued=datetime(2026, 1, 1))
        with self.assertRaises(ValueError):
            request("REQ", source=T0 - timedelta(microseconds=1))

    def test_first_receive_journals_pending_before_single_dispatch(self) -> None:
        core = CommandTransactionCore(timeout=timedelta(seconds=2))
        receipt = core.receive(request(), received_at=T0 + timedelta(milliseconds=10))

        self.assertEqual(receipt.disposition, Disposition.DISPATCH)
        self.assertTrue(receipt.should_dispatch)
        self.assertEqual(receipt.result.result_code, ResultCode.PENDING)
        evidence = receipt.result.to_dict()
        for field in (
            "request_id",
            "equipment_id",
            "command",
            "issued_timestamp",
            "source_timestamp",
            "ack_id",
            "result_code",
        ):
            self.assertIn(field, evidence)

    def test_identical_request_id_and_body_is_idempotent_replay(self) -> None:
        core = CommandTransactionCore()
        original = core.receive(request(), received_at=T0)
        replay = core.receive(request(), received_at=T0 + timedelta(seconds=1))

        self.assertEqual(replay.disposition, Disposition.REPLAY)
        self.assertFalse(replay.should_dispatch)
        self.assertEqual(replay.result.to_json(), original.result.to_json())

    def test_request_id_reuse_with_different_body_is_rejected_and_cached(self) -> None:
        core = CommandTransactionCore()
        original = core.receive(request(), received_at=T0)
        changed = request(command="CLOSE", issued=T0 + timedelta(milliseconds=1))
        first = core.receive(changed, received_at=T0 + timedelta(milliseconds=2))
        replay = core.receive(changed, received_at=T0 + timedelta(seconds=1))

        self.assertEqual(first.disposition, Disposition.REJECT)
        self.assertEqual(first.result.result_code, ResultCode.REQUEST_ID_MISMATCH)
        self.assertEqual(first.result.to_json(), replay.result.to_json())
        self.assertEqual(core.get("REQ-001"), original.result)

    def test_different_request_id_same_command_occurrence_is_duplicate(self) -> None:
        core = CommandTransactionCore()
        core.receive(request("REQ-001"), received_at=T0)
        duplicate = core.receive(request("REQ-002"), received_at=T0)

        self.assertEqual(duplicate.disposition, Disposition.REJECT)
        self.assertEqual(duplicate.result.result_code, ResultCode.DUPLICATE_REQUEST)
        self.assertIn("REQ-001", duplicate.result.detail)

    def test_out_of_order_is_per_equipment_and_equal_time_is_rejected(self) -> None:
        core = CommandTransactionCore(timeout=timedelta(seconds=30))
        latest_time = T0 + timedelta(seconds=10)
        core.receive(request("NEW", issued=latest_time), received_at=latest_time)

        older = core.receive(
            request("OLD", command="OPEN", issued=T0 + timedelta(seconds=9)),
            received_at=latest_time,
        )
        equal = core.receive(
            request("EQUAL", command="CLOSE", issued=latest_time),
            received_at=latest_time,
        )
        other = core.receive(
            request("OTHER", equipment="VCB-A03", issued=T0), received_at=latest_time
        )

        self.assertEqual(older.result.result_code, ResultCode.OUT_OF_ORDER)
        self.assertEqual(equal.result.result_code, ResultCode.OUT_OF_ORDER)
        self.assertEqual(other.disposition, Disposition.DISPATCH)

    def test_expired_before_dispatch_and_pending_timeout_are_terminal(self) -> None:
        core = CommandTransactionCore(timeout=timedelta(seconds=2))
        expired = core.receive(request("OLD"), received_at=T0 + timedelta(seconds=2))
        self.assertEqual(expired.result.result_code, ResultCode.TIMEOUT)
        self.assertFalse(expired.should_dispatch)

        pending_request = request("LIVE", issued=T0 + timedelta(seconds=3))
        pending = core.receive(pending_request, received_at=T0 + timedelta(seconds=3))
        timed_out = core.expire(now=T0 + timedelta(seconds=5))
        self.assertEqual(len(timed_out), 1)
        self.assertEqual(timed_out[0].ack_id, pending.result.ack_id)
        self.assertEqual(timed_out[0].result_code, ResultCode.TIMEOUT)
        replay = core.receive(pending_request, received_at=T0 + timedelta(seconds=10))
        self.assertEqual(replay.disposition, Disposition.REPLAY)
        self.assertEqual(replay.result, timed_out[0])

    def test_completion_validates_ack_order_and_conflicting_duplicate(self) -> None:
        core = CommandTransactionCore()
        pending = core.receive(request(), received_at=T0)
        with self.assertRaisesRegex(TransactionProtocolError, "ack_id mismatch"):
            core.complete(
                request_id="REQ-001",
                ack_id="ACK-WRONG",
                result_code=ResultCode.SUCCESS,
                source_timestamp=T0,
            )
        with self.assertRaisesRegex(TransactionProtocolError, "precedes"):
            core.complete(
                request_id="REQ-001",
                ack_id=pending.result.ack_id,
                result_code=ResultCode.SUCCESS,
                source_timestamp=T0 - timedelta(microseconds=1),
            )

        completed_at = T0 + timedelta(milliseconds=80)
        completed = core.complete(
            request_id="REQ-001",
            ack_id=pending.result.ack_id,
            result_code=ResultCode.SUCCESS,
            source_timestamp=completed_at,
            detail="VCB-A02 opened",
        )
        replay = core.complete(
            request_id="REQ-001",
            ack_id=pending.result.ack_id,
            result_code=ResultCode.SUCCESS,
            source_timestamp=completed_at,
            detail="VCB-A02 opened",
        )
        self.assertIs(replay, completed)
        with self.assertRaisesRegex(TransactionProtocolError, "conflicting duplicate"):
            core.complete(
                request_id="REQ-001",
                ack_id=pending.result.ack_id,
                result_code=ResultCode.REJECTED,
                source_timestamp=completed_at,
            )

    def test_unknown_and_rejected_requests_cannot_be_completed(self) -> None:
        core = CommandTransactionCore(timeout=timedelta(seconds=1))
        with self.assertRaisesRegex(TransactionProtocolError, "unknown"):
            core.complete(
                request_id="MISSING",
                ack_id="ACK-MISSING",
                result_code=ResultCode.SUCCESS,
                source_timestamp=T0,
            )
        rejected = core.receive(request(), received_at=T0 + timedelta(seconds=1))
        with self.assertRaisesRegex(TransactionProtocolError, "non-dispatched"):
            core.complete(
                request_id="REQ-001",
                ack_id=rejected.result.ack_id,
                result_code=ResultCode.SUCCESS,
                source_timestamp=T0 + timedelta(seconds=1),
            )

    def test_checkpoint_reconnect_replays_without_redispatch(self) -> None:
        core = CommandTransactionCore(timeout=timedelta(seconds=2))
        pending_request = request()
        pending = core.receive(pending_request, received_at=T0)
        checkpoint = core.to_json()

        restored = CommandTransactionCore.from_json(checkpoint)
        self.assertEqual(restored.to_json(), checkpoint)
        replay = restored.receive(
            pending_request, received_at=T0 + timedelta(milliseconds=500)
        )
        self.assertEqual(replay.disposition, Disposition.REPLAY)
        self.assertFalse(replay.should_dispatch)
        self.assertEqual(replay.result.ack_id, pending.result.ack_id)

        timed_out = restored.expire(now=T0 + timedelta(seconds=2))
        self.assertEqual(timed_out[0].result_code, ResultCode.TIMEOUT)

    def test_checkpoint_preserves_terminal_and_mismatch_replay(self) -> None:
        core = CommandTransactionCore()
        pending = core.receive(request(), received_at=T0)
        core.complete(
            request_id="REQ-001",
            ack_id=pending.result.ack_id,
            result_code=ResultCode.SUCCESS,
            source_timestamp=T0 + timedelta(milliseconds=80),
        )
        changed = request(command="OPEN", issued=T0 + timedelta(milliseconds=1))
        mismatch = core.receive(changed, received_at=T0 + timedelta(milliseconds=2))

        restored = CommandTransactionCore.from_json(core.to_json())
        terminal_replay = restored.receive(request(), received_at=T0 + timedelta(seconds=1))
        mismatch_replay = restored.receive(changed, received_at=T0 + timedelta(seconds=1))
        self.assertEqual(terminal_replay.result.result_code, ResultCode.SUCCESS)
        self.assertEqual(mismatch_replay.result.to_json(), mismatch.result.to_json())

    def test_serialization_is_canonical_and_scalar_safe(self) -> None:
        core = CommandTransactionCore()
        result = core.receive(request(), received_at=T0).result
        encoded = result.to_json()
        self.assertEqual(encoded, json.dumps(json.loads(encoded), sort_keys=True, separators=(",", ":")))
        self.assertTrue(all(isinstance(value, str) for value in result.to_scalar_map("cmd.").values()))
        self.assertEqual(serialize_results((result,)), f"[{encoded}]")

    def test_tampered_or_malformed_checkpoint_is_rejected(self) -> None:
        core = CommandTransactionCore()
        core.receive(request(), received_at=T0)
        state = json.loads(core.to_json())
        state["records"][0]["result"]["ack_id"] = "ACK-TAMPERED"
        with self.assertRaisesRegex(TransactionProtocolError, "identity mismatch"):
            CommandTransactionCore.from_json(json.dumps(state))
        with self.assertRaises(TransactionProtocolError):
            CommandTransactionCore.from_json("not-json")

        mismatch_core = CommandTransactionCore()
        mismatch_core.receive(request(), received_at=T0)
        mismatch_core.receive(
            request(command="OPEN", issued=T0 + timedelta(milliseconds=1)),
            received_at=T0 + timedelta(milliseconds=2),
        )
        mismatch_state = json.loads(mismatch_core.to_json())
        mismatch_state["conflicts"][0]["request_digest"] = "0" * 64
        with self.assertRaisesRegex(TransactionProtocolError, "digest mismatch"):
            CommandTransactionCore.from_json(json.dumps(mismatch_state))


if __name__ == "__main__":
    unittest.main()
