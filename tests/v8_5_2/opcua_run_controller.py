#!/usr/bin/env python3
"""Start an OpenModelica embedded OPC UA runtime with its Run control node."""

from __future__ import annotations

import argparse
import logging
import time


def connect_with_retry(endpoint: str, timeout_s: float):
    from opcua import Client

    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        client = Client(endpoint, timeout=10)
        try:
            client.connect()
            return client
        except Exception as exc:
            last_error = exc
            try:
                client.disconnect()
            except Exception:
                pass
            time.sleep(0.25)
    raise RuntimeError(f"could not connect to {endpoint}: {last_error}")


def main() -> int:
    logging.getLogger("opcua").setLevel(logging.ERROR)
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--connect-timeout", type=float, default=120.0)
    parser.add_argument("--advance-timeout", type=float, default=180.0)
    parser.add_argument("--real-time-factor", type=float, default=1.0)
    args = parser.parse_args()

    from opcua import ua

    client = connect_with_retry(args.endpoint, args.connect_timeout)
    try:
        run_node = client.get_node(ua.NodeId(10001, 0))
        scale_node = client.get_node(ua.NodeId(10002, 0))
        stop_node = client.get_node(ua.NodeId(10003, 0))
        time_node = client.get_node(ua.NodeId(10004, 0))

        before = float(time_node.get_value())
        scale_node.set_value(
            ua.Variant(float(args.real_time_factor), ua.VariantType.Double)
        )
        stop_node.set_value(ua.Variant(True, ua.VariantType.Boolean))
        run_node.set_value(ua.Variant(True, ua.VariantType.Boolean))

        deadline = time.monotonic() + args.advance_timeout
        current = before
        while current <= before + 1e-12:
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Run=true did not advance beyond {before}")
            time.sleep(0.02)
            current = float(time_node.get_value())

        print(
            f"RUN_READY endpoint={args.endpoint} "
            f"model_time_before={before} model_time_after={current}",
            flush=True,
        )
        return 0
    finally:
        client.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
