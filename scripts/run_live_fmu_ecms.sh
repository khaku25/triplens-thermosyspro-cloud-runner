#!/usr/bin/env bash
set -euo pipefail

# Commissioning gate for the real bidirectional path:
#   ECMS process --TCP command--> running OpenModelica FMU
#   ECMS process <--TCP telemetry-- FMI-solved physical outputs
# CSV files in outputs/live are post-receive audit artifacts only. They are
# never fed back into the FMU and are not used as inter-process transport.

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
cd "$project_root"

stop_time_s="${LIVE_STOP_TIME_S:-10}"
step_size_s="${LIVE_STEP_SIZE_S:-0.001}"
trip_time_s="${LIVE_TRIP_TIME_S:-2}"
openmodelica_image="openmodelica/openmodelica:v1.27.0-minimal"
thermosyspro_commit="db81ae1b5a6a85f6c6c7693244cafa6087e18ff5"
dependency_timeout="${OPENMODELICA_DEPENDENCY_TIMEOUT:-5m}"
fmu_build_timeout="${OPENMODELICA_FMU_BUILD_TIMEOUT:-38m}"

mkdir -p build/omhome vendor outputs
rm -rf "$project_root/outputs/live"
rm -f "$project_root/build/TripLens_CCPP_Live.fmu"
rm -f "$project_root/build/live-fmu-build.log"
mkdir -p "$project_root/outputs/live"

intervals="$(python3 - "$stop_time_s" "$step_size_s" <<'PY'
import math
import sys
stop = float(sys.argv[1])
step = float(sys.argv[2])
count = stop / step
if not math.isfinite(count) or count < 10 or not math.isclose(count, round(count), abs_tol=1e-9):
    raise SystemExit("LIVE_STOP_TIME_S must be an integer multiple of LIVE_STEP_SIZE_S")
print(round(count))
PY
)"

python3 scripts/render_modelica.py \
  --external-trip-input \
  --trip-time "$trip_time_s" \
  --trip-ramp-duration 2 \
  --stop-time "$stop_time_s" \
  --intervals "$intervals"

if [[ ! -e vendor/ThermoSysPro ]]; then
  git clone --no-checkout https://github.com/Dwarf-Planet-Project/ThermoSysPro.git vendor/ThermoSysPro
fi
if ! git -C vendor/ThermoSysPro rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "vendor/ThermoSysPro is incomplete or is not a Git checkout" >&2
  exit 1
fi
git -C vendor/ThermoSysPro checkout --detach "$thermosyspro_commit"
if [[ "$(git -C vendor/ThermoSysPro rev-parse HEAD)" != "$thermosyspro_commit" ]]; then
  echo "ThermoSysPro checkout does not match the pinned commit" >&2
  exit 1
fi

python3 scripts/patch_turbine_bypass_model.py \
  --source vendor/ThermoSysPro/ThermoSysPro/Examples/CombinedCyclePowerPlant/CombinedCycle_TripTAC.mo
python3 scripts/patch_stodola_turbine.py \
  vendor/ThermoSysPro/ThermoSysPro/WaterSteam/Machines/StodolaTurbine.mo

timeout --signal=TERM --kill-after=30s "$dependency_timeout" \
  docker run --rm \
    -v "$project_root/build/omhome:/root" \
    -v "$project_root:/workspace" \
    -w /workspace \
    "$openmodelica_image" \
    omc /workspace/modelica/install_dependencies.mos

timeout --signal=TERM --kill-after=30s "$fmu_build_timeout" \
  docker run --rm \
    -v "$project_root/build/omhome:/root" \
    -v "$project_root:/workspace" \
    -w /workspace \
    "$openmodelica_image" \
    omc /workspace/build/build_live_fmu.mos | tee "$project_root/build/live-fmu-build.log"

if grep -Eq 'Failed to build model|Error:' "$project_root/build/live-fmu-build.log"; then
  echo "OpenModelica reported an FMU build error" >&2
  exit 1
fi
if [[ ! -s build/TripLens_CCPP_Live.fmu ]]; then
  echo "OpenModelica did not create the live Co-Simulation FMU" >&2
  exit 1
fi

ready_file="$project_root/outputs/live/gateway-ready.json"
python3 scripts/live_fmu_gateway.py \
  --fmu "$project_root/build/TripLens_CCPP_Live.fmu" \
  --stop-time "$stop_time_s" \
  --step-size "$step_size_s" \
  --ready-file "$ready_file" \
  --output-dir "$project_root/outputs/live" \
  >"$project_root/outputs/live/gateway.log" 2>&1 &
gateway_pid=$!
cleanup_gateway() {
  if kill -0 "$gateway_pid" 2>/dev/null; then
    kill "$gateway_pid" 2>/dev/null || true
  fi
}
trap cleanup_gateway EXIT

for _ in $(seq 1 900); do
  if [[ -s "$ready_file" ]]; then
    break
  fi
  if ! kill -0 "$gateway_pid" 2>/dev/null; then
    wait "$gateway_pid" || true
    echo "live FMU gateway exited before opening its TCP listener" >&2
    sed -n '1,240p' "$project_root/outputs/live/gateway.log" >&2
    exit 1
  fi
  sleep 0.1
done
if [[ ! -s "$ready_file" ]]; then
  echo "live FMU gateway did not become ready" >&2
  exit 1
fi
gateway_port="$(python3 - "$ready_file" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["port"])
PY
)"

python3 scripts/live_ecms_client.py \
  --host 127.0.0.1 \
  --port "$gateway_port" \
  --stop-time "$stop_time_s" \
  --step-size "$step_size_s" \
  --trip-at "$trip_time_s" \
  --output-dir "$project_root/outputs/live"
wait "$gateway_pid"
trap - EXIT

python3 scripts/validate_live_network.py \
  --output-dir "$project_root/outputs/live" \
  --report "$project_root/outputs/live/LIVE-NETWORK-PROOF.json"
python3 scripts/build_live_ecms_dashboard.py \
  --capture "$project_root/outputs/live/ECMS-live-physical.csv" \
  --proof "$project_root/outputs/live/LIVE-NETWORK-PROOF.json" \
  --output "$project_root/outputs/live/ECMS-live-dashboard.html" \
  --preview-svg "$project_root/outputs/live/ECMS-live-dashboard.svg"

echo "LIVE FMU/ECMS closed-loop proof complete"
