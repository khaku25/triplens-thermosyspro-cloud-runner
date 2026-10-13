#!/usr/bin/env python3
"""Capture a bounded head/tail window from a verbose simulator log stream."""

from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--head-lines", type=int, default=300)
    parser.add_argument("--tail-lines", type=int, default=60_000)
    parser.add_argument("--progress-lines", type=int, default=1_000_000)
    args = parser.parse_args()
    for name in ("head_lines", "tail_lines", "progress_lines"):
        if getattr(args, name) < 0:
            parser.error(f"--{name.replace('_', '-')} must be non-negative")
    return args


def main() -> int:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tail: deque[str] = deque(maxlen=args.tail_lines)
    head: list[str] = []
    line_count = 0

    for line in sys.stdin:
        line_count += 1
        if line_count <= args.head_lines:
            head.append(line)
            sys.stdout.write(line)
            sys.stdout.flush()
        elif args.tail_lines:
            tail.append(line)
        if args.progress_lines and line_count % args.progress_lines == 0:
            print(f"CAPTURE_PROGRESS lines={line_count}", flush=True)

    omitted = max(0, line_count - len(head) - len(tail))
    with args.output.open("w", encoding="utf-8") as output:
        output.writelines(head)
        output.write(
            f"\nCAPTURE_WINDOW total_lines={line_count} omitted_lines={omitted} "
            f"tail_lines={len(tail)}\n"
        )
        output.writelines(tail)
    print(
        f"CAPTURE_COMPLETE total_lines={line_count} omitted_lines={omitted} "
        f"output={args.output}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
