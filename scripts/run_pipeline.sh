#!/usr/bin/env bash
set -euo pipefail

# Action ownership boundary:
#   ThermoSysPro/OpenModelica RAW physics only.
# This script must not normalize ProcessBus, evaluate DCS rules, synthesize
# ECMS/SOE, select an incident window, or attach a scenario/root-cause label.
#
# Semantic boundary:
#   2184.984 t/h / 893.75 K -> 540 t/h / 550 K is GT DERATE only.
#   GT DERATE remains separate. Canonical GT TRIP profiles are solved here and
#   must publish Modelica-produced command, breaker and thermal-process values.
#   The old run-vpp-gt-trip Python generator is replay-only and is not accepted
#   as physical proof.

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
cd "$project_root"

requested_event_time_s="${1:-600}"
requested_transition_duration_s="${2:-5}"
requested_stop_time_s="${3:-1000}"
requested_intervals="${4:-1000}"
sampling_profile="${5:-causal_100ms}"

event_time_s="$requested_event_time_s"
transition_duration_s="$requested_transition_duration_s"
stop_time_s="$requested_stop_time_s"
intervals="$requested_intervals"
normal_operation=false
derate_only=false
gt_trip=false
operating_mode="boundary-transient"

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
    # Bounded physical diagnostic profile. This changes only the native
    # OpenModelica CSV grid; it does not create millisecond alarm events.
    event_time_s=2
    transition_duration_s=5
    stop_time_s=10
    intervals=10000
    ;;
  normal_3min)
    event_time_s=600
    transition_duration_s=5
    stop_time_s=180
    intervals=1800
    normal_operation=true
    operating_mode="normal"
    ;;
  gt_derate_3min_10ms)
    # Canonical long GT DERATE profile. Exhaust flow/temperature are reduced,
    # while the embedded ST Trip trigger is suppressed beyond stop time.
    event_time_s=180
    transition_duration_s=5
    stop_time_s=190
    intervals=19000
    derate_only=true
    operating_mode="gt-derate"
    ;;
  gt_trip_commissioning_1ms)
    # Fast end-to-end proof: the command, breaker states and every thermal
    # response are emitted by the same OpenModelica result at 1 ms resolution.
    event_time_s=2
    transition_duration_s=2
    stop_time_s=10
    intervals=10000
    gt_trip=true
    operating_mode="gt-trip-physical"
    ;;
  gt_trip_full_100ms)
    # Competition replay horizon: 300 s pre-Trip and 120 s post-Trip.
    event_time_s=300
    transition_duration_s=5
    stop_time_s=420
    intervals=4200
    gt_trip=true
    operating_mode="gt-trip-physical-full"
    ;;
  *)
    echo "unknown sampling profile: $sampling_profile" >&2
    exit 2
    ;;
esac

echo "RAW-only ThermoSysPro run"
echo "Sampling profile: $sampling_profile"
echo "Operating mode: $operating_mode"
echo "Effective physical run: event=${event_time_s}s transition=${transition_duration_s}s stop=${stop_time_s}s intervals=$intervals"

openmodelica_image="openmodelica/openmodelica:v1.27.0-minimal"
dependency_timeout="${OPENMODELICA_DEPENDENCY_TIMEOUT:-5m}"
simulation_timeout="${OPENMODELICA_SIMULATION_TIMEOUT:-20m}"
if [[ "$sampling_profile" == "gt_derate_3min_10ms" ]]; then
  simulation_timeout="${OPENMODELICA_LONG_DERATE_TIMEOUT:-25m}"
fi
thermosyspro_commit="db81ae1b5a6a85f6c6c7693244cafa6087e18ff5"

mkdir -p build/omhome vendor

render_arguments=(
  --trip-time "$event_time_s"
  --trip-ramp-duration "$transition_duration_s"
  --stop-time "$stop_time_s"
  --intervals "$intervals"
)
if [[ "$normal_operation" == true ]]; then
  render_arguments+=(--normal-operation)
elif [[ "$derate_only" == true ]]; then
  render_arguments+=(--derate-only)
elif [[ "$gt_trip" == true ]]; then
  render_arguments+=(--gt-trip)
fi
python3 scripts/render_modelica.py "${render_arguments[@]}"

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

python3 scripts/patch_turbine_bypass_model.py \
  --source vendor/ThermoSysPro/ThermoSysPro/Examples/CombinedCyclePowerPlant/CombinedCycle_TripTAC.mo
python3 scripts/patch_stodola_turbine.py \
  vendor/ThermoSysPro/ThermoSysPro/WaterSteam/Machines/StodolaTurbine.mo
patched_model_sha256="$(sha256sum vendor/ThermoSysPro/ThermoSysPro/Examples/CombinedCyclePowerPlant/CombinedCycle_TripTAC.mo | cut -d' ' -f1)"

# A new Action run owns these generated paths. Clear only run-generated data.
rm -f "$project_root/build/thermosyspro_trip_tac_res.csv"
rm -f "$project_root/build/openmodelica-run.log"
rm -rf "$project_root/outputs"
mkdir -p "$project_root/outputs"

timeout --signal=TERM --kill-after=30s "$dependency_timeout" \
  docker run --rm \
    -v "$project_root/build/omhome:/root" \
    -v "$project_root:/workspace" \
    -w /workspace \
    "$openmodelica_image" \
    omc /workspace/modelica/install_dependencies.mos

timeout --signal=TERM --kill-after=30s "$simulation_timeout" \
  docker run --rm \
    -v "$project_root/build/omhome:/root" \
    -v "$project_root:/workspace" \
    -w /workspace \
    "$openmodelica_image" \
    omc /workspace/build/run.mos | tee "$project_root/build/openmodelica-run.log"

if grep -Eq 'resultFile = ""|Failed to build model|Simulation execution failed' \
    "$project_root/build/openmodelica-run.log"; then
  echo "OpenModelica reported an incomplete simulation" >&2
  exit 1
fi

if [[ ! -s build/thermosyspro_trip_tac_res.csv ]]; then
  echo "OpenModelica did not create a fresh non-empty result CSV" >&2
  exit 1
fi

# Byte-for-byte copy of the OpenModelica CSV. No row collapse, interpolation,
# tag rename, inferred command, alarm threshold, or ECMS event is applied.
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
  --openmodelica-image "$openmodelica_image" \
  --model-variant "HPBP_LPBP_PHYSICAL_V13_GT_TRIP_HANDOFF" \
  --source-patch-marker "TRIPLENS_VPP_TURBINE_BYPASS_PATCH_V12" \
  --patched-model-sha256 "$patched_model_sha256"

python3 scripts/validate_raw_outputs.py --output-dir outputs
