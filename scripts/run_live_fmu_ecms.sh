#!/usr/bin/env bash
set -euo pipefail

# Integration gate only. The FMU is built and physics-qualified upstream.
# This script proves two-process, full-duplex communication with the running FMU.
# CSV is written only after ECMS receives each TCP telemetry frame.

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
cd "$project_root"

fmu_path="${1:?usage: run_live_fmu_ecms.sh path/to/model.fmu}"
stop_time_s="${LIVE_STOP_TIME_S:-2}"
step_size_s="${LIVE_STEP_SIZE_S:-0.01}"
expected_fmu_sha256="${EXPECTED_FMU_SHA256:-883ca79109cc5277a01868068e916ebb1ad7df346b841820ff7b5ea66c76f387}"
output_dir="$project_root/outputs/live-main-fmu"
ready_file="$output_dir/gateway-ready.json"
runtime_library="${FMU_RUNTIME_LIBRARY:-}"
runtime_library_path="${FMU_RUNTIME_LIBRARY_PATH:-}"

if [[ ! -s "$fmu_path" ]]; then
  echo "FMU not found: $fmu_path" >&2
  exit 1
fi
actual_sha256="$(sha256sum "$fmu_path" | awk '{print $1}')"
if [[ "$actual_sha256" != "$expected_fmu_sha256" ]]; then
  echo "FMU SHA-256 mismatch: $actual_sha256" >&2
  exit 1
fi
python3 scripts/validate_live_fmu_contract.py --fmu "$fmu_path"

rm -rf "$output_dir"
mkdir -p "$output_dir"
gateway_command=(python3 scripts/live_fmu_gateway.py)
if [[ -n "$runtime_library" ]]; then
  if [[ ! -s "$runtime_library" ]]; then
    echo "OpenModelica runtime library not found: $runtime_library" >&2
    exit 1
  fi
  if [[ -z "$runtime_library_path" ]]; then
    runtime_library_path="$(dirname -- "$runtime_library")"
  fi
  gateway_command=(env \
    "LD_LIBRARY_PATH=$runtime_library_path${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    "LD_PRELOAD=$runtime_library" \
    python3 scripts/live_fmu_gateway.py)
fi
"${gateway_command[@]}" \
  --fmu "$fmu_path" \
  --stop-time "$stop_time_s" \
  --step-size "$step_size_s" \
  --ready-file "$ready_file" \
  --output-dir "$output_dir" \
  >"$output_dir/gateway.log" 2>&1 &
gateway_pid=$!
cleanup_gateway() {
  if kill -0 "$gateway_pid" 2>/dev/null; then
    kill "$gateway_pid" 2>/dev/null || true
  fi
}
trap cleanup_gateway EXIT

for _ in $(seq 1 900); do
  if [[ -s "$ready_file" ]]; then break; fi
  if ! kill -0 "$gateway_pid" 2>/dev/null; then
    wait "$gateway_pid" || true
    sed -n '1,240p' "$output_dir/gateway.log" >&2
    exit 1
  fi
  sleep 0.1
done
if [[ ! -s "$ready_file" ]]; then
  echo "FMU gateway did not become ready" >&2
  exit 1
fi
gateway_port="$(python3 - "$ready_file" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["port"])
PY
)"

python3 scripts/live_ecms_client.py \
  --host 127.0.0.1 \
  --port "$gateway_port" \
  --stop-time "$stop_time_s" \
  --step-size "$step_size_s" \
  --output-dir "$output_dir"
wait "$gateway_pid"
trap - EXIT

python3 scripts/validate_live_network.py \
  --output-dir "$output_dir" \
  --expected-fmu-sha256 "$expected_fmu_sha256" \
  --report "$output_dir/LIVE-NETWORK-PROOF.json"
python3 scripts/build_live_ecms_dashboard.py \
  --capture "$output_dir/ECMS-live-physical.csv" \
  --proof "$output_dir/LIVE-NETWORK-PROOF.json" \
  --output "$output_dir/ECMS-live-dashboard.html" \
  --preview-svg "$output_dir/ECMS-live-dashboard.svg"

echo "LIVE_MAIN_FMU_ECMS_INTEGRATION_PASS"
