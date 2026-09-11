from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_solver_health import classify_line, evaluate  # noqa: E402


ALLOWLIST = ROOT / "config" / "solver_health_allowlist_v1.json"
SCRIPT = ROOT / "scripts" / "check_solver_health.py"
RUNTIME_OK = """\
LOG_SUCCESS | info | The initialization finished successfully without homotopy method.
LOG_STDOUT | info | The embedded server is initialized.
"""


class SolverHealthGateTests(unittest.TestCase):
    def write_logs(self, directory: Path, build: str, runtime: str) -> tuple[Path, Path]:
        build_path = directory / "build.log"
        runtime_path = directory / "runtime.log"
        build_path.write_text(build, encoding="utf-8")
        runtime_path.write_text(runtime, encoding="utf-8")
        return build_path, runtime_path

    def test_clean_logs_pass_and_record_hashes_and_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            build, runtime = self.write_logs(Path(tmp), "Build completed\n", RUNTIME_OK)
            report = evaluate([build], [runtime], ALLOWLIST)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["summary"]["unexpected_count"], 0)
        self.assertTrue(all(item["sha256"] for item in report["inputs"]))
        self.assertEqual(len(report["inputs"][1]["observed_markers"]), 2)

    def test_critical_runtime_findings_cannot_be_allowlisted(self) -> None:
        runtime = RUNTIME_OK + "\n".join(
            (
                "LOG_ASSERT | debug | Division by zero bpro.R / p in function context",
                "LOG_STDOUT | warning | While solving non-linear system an assertion failed at time 27.0.",
                "LOG_ASSERT | debug | Solving linear system 7252 failed at time=87.1.",
                "state became NaN",
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            build, runtime_path = self.write_logs(Path(tmp), "Build completed\n", runtime)
            report = evaluate([build], [runtime_path], ALLOWLIST)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(
            report["summary"]["unexpected_counts_by_category"],
            {
                "assertion_failure": 1,
                "division_by_zero": 1,
                "non_finite_value": 1,
                "solver_failure": 1,
            },
        )
        self.assertTrue(
            all(row["reason"] == "critical_category" for row in report["unexpected_evidence"])
        )

    def test_exact_vendor_warning_is_allowlisted(self) -> None:
        warning = (
            "[/workspace/vendor/ThermoSysPro/ThermoSysPro/WaterSteam/Volumes/VolumeC.mo:"
            "1:1-1:2:writable] Warning: Connector C1 is not balanced: The number of "
            "potential variables (4) is not equal to the number of flow variables (0).\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            build, runtime = self.write_logs(Path(tmp), warning, RUNTIME_OK)
            report = evaluate([build], [runtime], ALLOWLIST)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["summary"]["allowlisted_count"], 1)
        self.assertEqual(
            report["allowlisted_evidence"][0]["allowlist_rule_id"],
            "TSP31_VENDOR_CONNECTOR_BALANCE",
        )

    def test_changed_or_project_warning_is_not_hidden(self) -> None:
        warning = "[/workspace/modelica/Other.mo:1:1] Warning: Connector C1 is not balanced.\n"
        with tempfile.TemporaryDirectory() as tmp:
            build, runtime = self.write_logs(Path(tmp), warning, RUNTIME_OK)
            report = evaluate([build], [runtime], ALLOWLIST)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["unexpected_evidence"][0]["reason"], "not_allowlisted")

    def test_allowlist_budget_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            custom = directory / "allowlist.json"
            custom.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "description": "test",
                        "rules": [
                            {
                                "id": "ONE_WARNING",
                                "stage": "build",
                                "category": "warning",
                                "pattern": "^Warning: reviewed diagnostic$",
                                "max_occurrences": 1,
                                "justification": "This exact diagnostic is accepted once for a unit test only.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            build, runtime = self.write_logs(
                directory,
                "Warning: reviewed diagnostic\nWarning: reviewed diagnostic\n",
                RUNTIME_OK,
            )
            report = evaluate([build], [runtime], custom)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["summary"]["allowlisted_count"], 1)
        self.assertEqual(report["unexpected_evidence"][0]["reason"], "allowlist_budget_exceeded")

    def test_missing_runtime_marker_and_missing_file_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            build = directory / "build.log"
            build.write_text("Build completed\n", encoding="utf-8")
            report = evaluate([build], [directory / "missing.log"], ALLOWLIST)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["summary"]["unexpected_counts_by_category"], {"missing_input": 1})

        with tempfile.TemporaryDirectory() as tmp:
            build, runtime = self.write_logs(Path(tmp), "Build completed\n", "runtime stopped\n")
            report = evaluate([build], [runtime], ALLOWLIST)
        self.assertEqual(report["summary"]["unexpected_counts_by_category"], {"missing_success_marker": 2})

    def test_information_does_not_look_like_infinity(self) -> None:
        self.assertIsNone(classify_line("For more information use -lv LOG_LS."))

    def test_cli_writes_report_even_when_gate_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            build, runtime = self.write_logs(
                directory,
                "Build completed\n",
                RUNTIME_OK + "LOG_ASSERT | debug | Division by zero x / y\n",
            )
            output = directory / "solver-health.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--build-log",
                    str(build),
                    "--runtime-log",
                    str(runtime),
                    "--output",
                    str(output),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(completed.returncode, 1)
        self.assertIn("SOLVER_HEALTH_FAIL", completed.stdout)
        self.assertEqual(report["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
