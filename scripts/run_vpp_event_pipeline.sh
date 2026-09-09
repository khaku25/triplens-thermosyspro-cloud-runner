#!/usr/bin/env bash
set -euo pipefail

# VPP event bundle boundary:
#   1. ThermoSysPro/OpenModelica produces physical values and Boolean logic.
#   2. export_vpp_events.py serializes state transitions only.
#   3. The alarm console displays and filters; it does not calculate alarms.

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
cd "$project_root"

event_time_s="${1:-10}"
coastdown_duration_s="${2:-5}"
stop_time_s="${3:-70}"
intervals="${4:-700}"
final_rpm="${5:-1000}"

output_dir="$project_root/outputs/vpp-event"
result_file="$project_root/build/triplens_vpp_event_res.csv"
logic_rules="$project_root/config/vpp_event_logic_provisional.csv"
openmodelica_image="openmodelica/openmodelica:v1.27.0-minimal"
thermosyspro_commit="db81ae1b5a6a85f6c6c7693244cafa6087e18ff5"

echo "ThermoSysPro VPP internal-logic run"
echo "physical_adapter=VALIDATED_BFP_BOUNDARY"
echo "event=${event_time_s}s coastdown=${coastdown_duration_s}s final_rpm=$final_rpm stop=${stop_time_s}s intervals=$intervals"
echo "alarm_decision_owner=MODELICA_VPP_LOGIC_RUNTIME"

mkdir -p build/omhome vendor "$output_dir"

if [[ ! -d vendor/ThermoSysPro/.git ]]; then
  if [[ -e vendor/ThermoSysPro ]]; then
    echo "vendor/ThermoSysPro exists but is not a complete Git checkout" >&2
    exit 1
  fi
  git clone --no-checkout https://github.com/Dwarf-Planet-Project/ThermoSysPro.git vendor/ThermoSysPro
fi
if ! git -C vendor/ThermoSysPro rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "vendor/ThermoSysPro is incomplete or is not a Git checkout" >&2
  exit 1
fi
git -C vendor/ThermoSysPro checkout --detach "$thermosyspro_commit"
test "$(git -C vendor/ThermoSysPro rev-parse HEAD)" = "$thermosyspro_commit"
test -f vendor/ThermoSysPro/ThermoSysPro/package.mo

python3 scripts/render_vpp_event_validated.py \
  --event-time "$event_time_s" \
  --coastdown-duration "$coastdown_duration_s" \
  --stop-time "$stop_time_s" \
  --intervals "$intervals" \
  --final-rpm "$final_rpm" \
  --rules "$logic_rules"

rm -f "$result_file"
rm -f \
  "$output_dir/VPP_RAW.csv" \
  "$output_dir/VPP_EVENT.csv" \
  "$output_dir/DCS1_EVENT.csv" \
  "$output_dir/DCS2_EVENT.csv" \
  "$output_dir/VPP_LOGIC_SNAPSHOT.csv" \
  "$output_dir/vpp-event-manifest.json"

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
  omc /workspace/build/run_vpp_event.mos | tee build/vpp_event.log

if grep -Fq 'resultFile = ""' build/vpp_event.log || \
   grep -Fq 'Simulation execution failed' build/vpp_event.log; then
  echo "OpenModelica reported a failed VPP simulation" >&2
  exit 1
fi
if [[ ! -s "$result_file" ]]; then
  echo "OpenModelica did not create a fresh non-empty VPP result CSV" >&2
  exit 1
fi
result_lines="$(wc -l < "$result_file")"
if (( result_lines < 3 )); then
  echo "OpenModelica VPP result needs a header and at least two data rows" >&2
  exit 1
fi

cp "$result_file" "$output_dir/VPP_RAW.csv"
if ! cmp -s "$result_file" "$output_dir/VPP_RAW.csv"; then
  echo "VPP_RAW.csv differs from the native OpenModelica result" >&2
  exit 1
fi

python3 scripts/export_vpp_events.py \
  --raw "$output_dir/VPP_RAW.csv" \
  --rules "$logic_rules" \
  --output "$output_dir/VPP_EVENT.csv" \
  --dcs1-output "$output_dir/DCS1_EVENT.csv" \
  --dcs2-output "$output_dir/DCS2_EVENT.csv" \
  --logic-snapshot "$output_dir/VPP_LOGIC_SNAPSHOT.csv" \
  --manifest "$output_dir/vpp-event-manifest.json"

python3 scripts/validate_vpp_event_bundle.py --output-dir "$output_dir"

echo "VPP_RAW=$output_dir/VPP_RAW.csv"
echo "VPP_EVENT=$output_dir/VPP_EVENT.csv"
echo "DCS1_EVENT=$output_dir/DCS1_EVENT.csv"
echo "DCS2_EVENT=$output_dir/DCS2_EVENT.csv"
