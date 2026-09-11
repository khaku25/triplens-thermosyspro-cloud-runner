from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TripSemanticsAuditTests(unittest.TestCase):
    def test_checked_in_contract_passes_standalone_semantics_audit(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "config" / "audit_trip_semantics.py")],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        report = json.loads((ROOT / "outputs" / "trip_semantics_audit.json").read_text())
        self.assertTrue(report["pass"])
        self.assertEqual(report["common_trip_causes_checked"], 9)
        self.assertEqual(report["errors"], [])


if __name__ == "__main__":
    unittest.main()
