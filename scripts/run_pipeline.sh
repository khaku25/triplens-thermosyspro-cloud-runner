#!/usr/bin/env bash
set -euo pipefail

# Action ownership boundary:
#   ThermoSysPro/OpenModelica RAW physics only.
# This runner is the validated GT DERATE process-boundary adapter. It is NOT a
# GT Trip adapter. Canonical GT Trip is breaker-open semantics; native GT
# thermodynamic shutdown/rundown remains a separate pending adapter.
#
# This script must not normalize ProcessBus, evaluate DCS rules, synthesize
# ECMS/SOE, select an incident window, or attach a scenario/root-cause label.

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
cd "$project_root"

requested_event_time_s="${1:-600}"
requested_transition_duration_s="${2:-5}"
requested_stop_time_s="${3:-1000}"
requested_intervals="${4:-1000}"
sampling_profile="${5:-causal_100ms}"

derate_time_s="$requested_event_time_s"
derate_duration_s="$requested_transition_duration_s"
stop_time_s="$requested_stop_time_s"
intervals="$requested_intervals"

case "$sampling_profile" in
  standard) ;;
  causal_100ms)
    intervals="$(python3 - "$stop_time_s" <<'PY'
import math
import sys
stop = float(sys.argv[1])
intervals = stop * 10
if not math.isfinite(stop) or stop <= 0 or not math.isclose(intervals, round(intervals), abs_tol=1e-9):
    raise SystemExit("causal_100ms requires a positive stop time aligned to 0.1 s")
print(round(intervals))
PY
)"
    ;;
  incident_1ms)
    derate_time_s=2
    derate_duration_s=5
    stop_time_s=10
    intervals=10000
    ;;
  *)
    echo "unknown sampling profile: $sampling_profile" >&2
    exit 2
    ;;
esac

echo "RAW-only ThermoSysPro GT DERATE run"
echo "Sampling profile: $sampling_profile"
echo "Effective physical run: derate=${derate_time_s}s transition=${derate_duration_s}s stop=${stop_time_s}s intervals=$intervals"
echo "Canonical semantics: 150/550 boundary reduction = DERATE; GT Trip requires 52GT.CLOSED=0"

openmodelica_image="openmodelica/openmodelica:v1.27.0-minimal"
thermosyspro_commit="db81ae1b5a6a85f6c6c7693244cafa6087e18ff5"

mkdir -p build/omhome vendor

python3 scripts/render_modelica.py \
  --derate-time "$derate_time_s" \
  --derate-ramp-duration "$derate_duration_s" \
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
actual_thermosyspro_commit="$(git -C vendor/ThermoSysPro rev-parse HEAD)"
if [[ "$actual_thermosyspro_commit" != "$thermosyspro_commit" ]]; then
  echo "ThermoSysPro checkout does not match the pinned commit" >&2
  exit 1
fi
if [[ ! -f vendor/ThermoSysPro/ThermoSysPro/package.mo ]]; then
  echo "ThermoSysPro package.mo is missing after checkout" >&2
  exit 1
fi

rm -f "$project_root/build/thermosyspro_trip_tac_res.csv"
rm -rf "$project_root/outputs"
mkdir -p "$project_root/outputs"

docker run --rm \
  -v "$project_root/build/omhome:/root" \
  -v "$project_root:/workspace" \
  -w /workspace \
  "$openmodelica_image" \
  omc /workspace/modelica/install_dependencies.mos

docker run --rm \
  -v "$project_root/build/omhome:/root" \
  -v "$project_root:/workspace" \
  -w /workspace \
  "$openmodelica_image" \
  omc /workspace/build/run.mos

if [[ ! -s build/thermosyspro_trip_tac_res.csv ]]; then
  echo "OpenModelica did not create a fresh non-empty result CSV" >&2
  exit 1
fi

cp build/thermosyspro_trip_tac_res.csv outputs/thermosyspro-raw.csv
if ! cmp -s build/thermosyspro_trip_tac_res.csv outputs/thermosyspro-raw.csv; then
  echo "RAW copy differs from the native OpenModelica result" >&2
  exit 1
fi

python3 scripts/build_raw_manifest.py \
  --raw-file outputs/thermosyspro-raw.csv \
  --output outputs/raw-manifest.json \
  --sampling-profile "$sampling_profile" \
  --stop-time "$stop_time_s" \
  --output-intervals "$intervals" \
  --thermosyspro-commit "$thermosyspro_commit" \
  --openmodelica-image "$openmodelica_image"

python3 scripts/validate_raw_outputs.py --output-dir outputs
