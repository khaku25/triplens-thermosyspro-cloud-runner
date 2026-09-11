#!/usr/bin/env python3
"""Dispatch the MATLAB/OPC UA runner and import its physical capture into Cloud ECMS.

GitHub owns only the Simulink -> OPC UA -> ThermoSysPro physical exchange.  This
program downloads that immutable receive capture and runs the ProcessBus/DCS/ECMS
layers locally, so alarm logic and labels never move into the GitHub physics job.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path


API_VERSION = "2026-03-10"
DEFAULT_REPOSITORY = "khaku25/triplens-matlab-cosim-runner"
DEFAULT_REF = "codex/matlab-opcua-vpp-20260910"
DEFAULT_WORKFLOW = "matlab-native-opcua-ecms.yml"
ARTIFACT_PREFIX = "matlab-ecms-native-opcua-"
THERMOSYSPRO_COMMIT = "db81ae1b5a6a85f6c6c7693244cafa6087e18ff5"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class GitHubClient:
    def __init__(self, repository: str, token: str) -> None:
        if repository.count("/") != 1:
            raise ValueError("repository must use owner/name form")
        if not token.strip():
            raise ValueError("GitHub token is empty")
        self.repository = repository
        self.token = token.strip()
        self.base = f"https://api.github.com/repos/{repository}"

    def _request(self, method: str, path: str, payload: object | None = None) -> bytes:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base + path,
            data=body,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "TripLens-Cloud-OPCUA-Bridge/1.0",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub API {method} {path} failed ({exc.code}): {detail}") from exc

    def json(self, method: str, path: str, payload: object | None = None) -> dict[str, object]:
        raw = self._request(method, path, payload)
        if not raw:
            return {}
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise RuntimeError("GitHub API returned a non-object JSON response")
        return value

    def dispatch(self, workflow: str, ref: str) -> dict[str, object]:
        response = self.json(
            "POST", f"/actions/workflows/{workflow}/dispatches", {"ref": ref}
        )
        run_id = response.get("workflow_run_id")
        if not isinstance(run_id, int) or run_id <= 0:
            raise RuntimeError("GitHub dispatch response did not contain workflow_run_id")
        return response

    def wait_for_run(self, run_id: int, timeout_seconds: float, poll_seconds: float) -> dict[str, object]:
        deadline = time.monotonic() + timeout_seconds
        previous = ""
        while time.monotonic() < deadline:
            run = self.json("GET", f"/actions/runs/{run_id}")
            status = str(run.get("status", ""))
            if status != previous:
                print(f"GITHUB_OPCUA_RUN status={status or 'unknown'} run_id={run_id}", flush=True)
                previous = status
            if status == "completed":
                if run.get("conclusion") != "success":
                    raise RuntimeError(
                        f"GitHub OPC UA run ended with {run.get('conclusion')}: {run.get('html_url', '')}"
                    )
                return run
            time.sleep(poll_seconds)
        raise TimeoutError(f"GitHub OPC UA run {run_id} exceeded the configured timeout")

    def artifact(self, run_id: int) -> dict[str, object]:
        response = self.json("GET", f"/actions/runs/{run_id}/artifacts?per_page=100")
        artifacts = response.get("artifacts", [])
        matches = [
            item for item in artifacts
            if isinstance(item, dict)
            and str(item.get("name", "")).startswith(ARTIFACT_PREFIX)
            and not bool(item.get("expired", False))
        ]
        if len(matches) != 1:
            names = [str(item.get("name", "")) for item in artifacts if isinstance(item, dict)]
            raise RuntimeError(f"expected one live OPC UA artifact, found {matches!r}; available={names}")
        return matches[0]

    def download_artifact(self, artifact_id: int, destination: Path) -> None:
        destination.write_bytes(self._request("GET", f"/actions/artifacts/{artifact_id}/zip"))
        if not zipfile.is_zipfile(destination):
            raise RuntimeError("downloaded GitHub artifact is not a ZIP archive")


def safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            target = (destination / info.filename).resolve()
            if root != target and root not in target.parents:
                raise RuntimeError(f"unsafe path in GitHub artifact: {info.filename}")
        bundle.extractall(destination)


def find_one(root: Path, name: str) -> Path:
    matches = [path for path in root.rglob(name) if path.is_file()]
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one {name}, found {len(matches)}")
    return matches[0]


def run_engine(
    package_root: Path,
    capture: Path,
    staging: Path,
    event_time: float,
    a_settings: Path,
    a_equipment: Path,
) -> None:
    command = [
        sys.executable,
        str(package_root / "scripts" / "vpp_alarm_engine.py"),
        "--raw", str(capture),
        "--input-kind", "raw",
        "--event-time", f"{event_time:.12g}",
        "--output-dir", str(staging),
        "--a-settings", str(a_settings),
        "--a-equipment", str(a_equipment),
        "--ecms-sampling-profile", "incident_1ms",
    ]
    completed = subprocess.run(
        command, cwd=package_root, check=False, capture_output=True, text=True
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"Cloud RAW-to-ECMS conversion failed: {detail}")
    if completed.stdout.strip():
        print(completed.stdout.strip(), flush=True)


def import_artifact(
    artifact_dir: Path,
    package_root: Path,
    output_root: Path,
    github_run_id: int,
    github_run_url: str,
    repository: str,
    ref: str,
    artifact_name: str,
    a_settings: Path,
    a_equipment: Path,
    update_latest: bool,
) -> Path:
    capture = find_one(artifact_dir, "ECMS-native-physical.csv")
    proof_path = find_one(artifact_dir, "native-opcua-proof.json")
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    if proof.get("status") != "PASS":
        raise RuntimeError("native OPC UA proof status is not PASS")
    if proof.get("transport_scope") != "REAL_OPC_UA_TCP_INSIDE_GITHUB_HOSTED_RUNNER":
        raise RuntimeError("artifact does not prove real OPC UA TCP inside the GitHub runner")
    if proof.get("scenario_id") != "RUNNING_52GT_OPEN_TO_GT_TRIP":
        raise RuntimeError("artifact is not the running-52GT-open causal scenario")
    if proof.get("root_cause") != "52GT_OPEN_WHILE_GT_IN_SERVICE":
        raise RuntimeError("artifact does not identify 52GT open as the root input")
    if proof.get("causal_order_verified") is not True:
        raise RuntimeError("artifact does not prove 52GT-open-before-GT-Trip ordering")
    if proof.get("actual_plant_logic_used") is not False:
        raise RuntimeError("artifact unexpectedly claims actual plant logic")
    event_time = float(proof.get("root_cause_time_s"))
    if not math.isfinite(event_time) or event_time <= 0:
        raise RuntimeError("OPC UA proof has an invalid root_cause_time_s")
    capture_hash = sha256(capture)

    output_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_name = f"MATLAB_GITHUB_OPCUA_{stamp}_{github_run_id}"
    final = output_root / run_name
    staging = output_root / f".staging_{run_name}"
    if final.exists() or staging.exists():
        raise RuntimeError(f"Cloud run folder already exists: {final}")
    staging.mkdir()
    try:
        received = staging / "github-opcua-received.csv"
        shutil.copyfile(capture, received)
        shutil.copyfile(proof_path, staging / "native-opcua-proof.json")
        run_engine(package_root, received, staging, event_time, a_settings, a_equipment)
        if sha256(capture) != capture_hash or sha256(received) != capture_hash:
            raise RuntimeError("OPC UA receive capture changed during Cloud conversion")

        aliases = {
            "ProcessBus.csv": "processbus.csv",
            "ECMS-trend.csv": "ecms-trend.csv",
            "ECMS.csv": "ecms-events.csv",
            "ECMS-feeders.csv": "ecms-feeders.csv",
        }
        for source, destination in aliases.items():
            source_path = staging / source
            if not source_path.is_file():
                raise RuntimeError(f"Cloud conversion did not create {source}")
            shutil.copyfile(source_path, staging / destination)

        config_dir = staging / "config"
        config_dir.mkdir()
        shutil.copyfile(a_settings, config_dir / "ecms_a_settings.csv")
        shutil.copyfile(a_equipment, config_dir / "ecms_a_equipment.csv")

        vpp_manifest_path = staging / "VPP.MANIFEST.json"
        manifest = json.loads(vpp_manifest_path.read_text(encoding="utf-8"))
        manifest.update({
            "schema_version": "3.1-github-opcua",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "run_id": run_name,
            "runtime": {
                "engine": "THERMOSYSPRO_OPENMODELICA_OPCUA_GITHUB",
                "thermosyspro_used": True,
                "thermosyspro_repository": "Dwarf-Planet-Project/ThermoSysPro",
                "thermosyspro_commit": THERMOSYSPRO_COMMIT,
                "opcua_transport_scope": proof["transport_scope"],
                "opcua_client_implementation": proof.get("client_implementation", ""),
                "matlab_release": proof.get("matlab_release", ""),
            },
            "scenario": {
                "id": proof["scenario_id"],
                "root_cause": proof["root_cause"],
                "root_cause_time_s": event_time,
                "causal_order_verified": True,
                "actual_plant_logic_used": False,
                "policy_status": proof.get("breaker_open_trip_policy", ""),
            },
            "github": {
                "repository": repository,
                "ref": ref,
                "workflow": DEFAULT_WORKFLOW,
                "run_id": github_run_id,
                "run_url": github_run_url,
                "artifact_name": artifact_name,
            },
            "opcua_capture": {
                "file": received.name,
                "sha256": capture_hash,
                "mutated": False,
                "root_cause_time_s": event_time,
                "physical_trip_readback_time_s": proof.get(
                    "opcua_trip_readback_time_s"
                ),
            },
            "root_cause_label_injected": False,
        })
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        required = [*aliases.values(), "manifest.json"]
        missing = [name for name in required if not (staging / name).is_file()]
        if missing:
            raise RuntimeError("Cloud run is incomplete: " + ", ".join(missing))
        staging.rename(final)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    if update_latest:
        expected_output_root = (package_root / "runs").resolve()
        if output_root != expected_output_root:
            raise RuntimeError("latest_run.txt may only point inside the package runs folder")
        pointer = package_root / "latest_run.txt"
        temporary = package_root / f".latest_run_{run_name}.tmp"
        temporary.write_text(f"runs/{run_name}\n", encoding="utf-8")
        os.replace(temporary, pointer)
    return final


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--ref", default=DEFAULT_REF)
    parser.add_argument("--workflow", default=DEFAULT_WORKFLOW)
    parser.add_argument("--token-env", default="TRIPLENS_GITHUB_TOKEN")
    parser.add_argument("--timeout-minutes", type=float, default=240)
    parser.add_argument("--poll-seconds", type=float, default=15)
    parser.add_argument("--a-settings", type=Path)
    parser.add_argument("--a-equipment", type=Path)
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--github-run-id", type=int, default=0)
    parser.add_argument("--github-run-url", default="")
    parser.add_argument("--artifact-name", default="local-test-artifact")
    parser.add_argument(
        "--update-latest",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Atomically update <package>/latest_run.txt after a successful import.",
    )
    args = parser.parse_args()
    if args.timeout_minutes <= 0 or args.poll_seconds <= 0:
        parser.error("timeout and poll period must be positive")
    return args


def main() -> int:
    args = parse_args()
    package_root = args.package_root.resolve()
    output_root = args.output_root.resolve()
    a_settings = (args.a_settings or package_root / "config" / "ecms_a_settings.csv").resolve()
    a_equipment = (args.a_equipment or package_root / "config" / "ecms_a_equipment.csv").resolve()
    for path, label in ((a_settings, "A settings"), (a_equipment, "A equipment")):
        if not path.is_file():
            raise RuntimeError(f"{label} file does not exist: {path}")

    if args.artifact_dir:
        artifact_dir = args.artifact_dir.resolve()
        run_id = args.github_run_id
        run_url = args.github_run_url
        artifact_name = args.artifact_name
        if run_id < 0:
            raise ValueError("github run id must be non-negative")
        final = import_artifact(
            artifact_dir, package_root, output_root, run_id, run_url,
            args.repository, args.ref, artifact_name, a_settings, a_equipment,
            args.update_latest,
        )
    else:
        token = os.environ.get(args.token_env, "")
        if not token:
            raise RuntimeError(
                f"{args.token_env} is not set; create a fine-grained token with Actions read/write "
                f"for {args.repository} and store it only in that environment variable"
            )
        client = GitHubClient(args.repository, token)
        dispatch = client.dispatch(args.workflow, args.ref)
        run_id = int(dispatch["workflow_run_id"])
        run_url = str(dispatch.get("html_url", ""))
        print(f"GITHUB_OPCUA_DISPATCHED run_id={run_id} url={run_url}", flush=True)
        run = client.wait_for_run(
            run_id, args.timeout_minutes * 60.0, args.poll_seconds
        )
        run_url = str(run.get("html_url", run_url))
        artifact = client.artifact(run_id)
        artifact_id = int(artifact["id"])
        artifact_name = str(artifact["name"])
        with tempfile.TemporaryDirectory(prefix="triplens_github_opcua_") as directory:
            temporary = Path(directory)
            archive = temporary / "artifact.zip"
            extracted = temporary / "artifact"
            client.download_artifact(artifact_id, archive)
            safe_extract(archive, extracted)
            final = import_artifact(
                extracted, package_root, output_root, run_id, run_url,
                args.repository, args.ref, artifact_name, a_settings, a_equipment,
                args.update_latest,
            )

    result = {
        "RunFolder": str(final),
        "GitHubRunId": run_id,
        "RunUrl": run_url,
        "ArtifactName": artifact_name,
        "Engine": "THERMOSYSPRO_OPENMODELICA_OPCUA_GITHUB",
    }
    print("TRIPLENS_GITHUB_BRIDGE_RESULT=" + json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
