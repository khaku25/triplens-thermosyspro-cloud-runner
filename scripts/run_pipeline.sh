#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
cd "$project_root"

requested_trip_time_s="${1:-600}"
requested_trip_ramp_duration_s="${2:-5}"
requested_stop_time_s="${3:-1000}"
requested_intervals="${4:-1000}"
fault_preset="${5:-none}"
command_scenario="${6:-none}"
sampling_profile="${7:-standard}"
incident_pre_ms="${8:-2000}"
incident_post_ms="${9:-5000}"
incident_period_ms=1

trip_time_s="$requested_trip_time_s"
trip_ramp_duration_s="$requested_trip_ramp_duration_s"
stop_time_s="$requested_stop_time_s"
intervals="$requested_intervals"

if [[ ! "$incident_pre_ms" =~ ^[0-9]+$ || ! "$incident_post_ms" =~ ^[0-9]+$ ]]; then
  echo "incident window values must be non-negative integer milliseconds" >&2
  exit 2
fi

case "$sampling_profile" in
  standard) ;;
  incident_1ms)
    # A bounded diagnostic preset keeps the per-sample feeder export small
    # enough for GitHub Actions and MATLAB Online. The raw
    # ThermoSysPro result is genuinely sampled every 1 ms for this entire run;
    # the ECMS export remains 20 ms outside the requested incident window.
    trip_time_s=2
    trip_ramp_duration_s=5
    stop_time_s=10
    intervals=10000
    if [[ "$command_scenario" == "bfp_trip" ]]; then
      echo "bfp_trip occurs at 100 s and cannot run in the 0-10 s incident_1ms preset" >&2
      exit 2
    fi
    ;;
  *)
    echo "unknown sampling profile: $sampling_profile" >&2
    exit 2
    ;;
esac

echo "Sampling profile: $sampling_profile"
echo "Effective run: trip=${trip_time_s}s ramp=${trip_ramp_duration_s}s stop=${stop_time_s}s intervals=$intervals"

case "$fault_preset" in
  none|gtg_breaker_fail|uat_a_fault|uat_b_fault|gt_transformer_receive_fail|st_transformer_receive_fail|bus_a_fault|bus_b_fault|grid_loss|relay_fail|ecms_comms_loss) ;;
  *)
    echo "unknown fault preset: $fault_preset" >&2
    exit 2
    ;;
esac

command_args=()
case "$command_scenario" in
  none) ;;
  bfp_trip)
    command_args=(--commands examples/bfp_trip_commands.csv)
    ;;
  *)
    echo "unknown command scenario: $command_scenario" >&2
    exit 2
    ;;
esac

openmodelica_image="openmodelica/openmodelica:v1.27.0-minimal"
thermosyspro_commit="db81ae1b5a6a85f6c6c7693244cafa6087e18ff5"

mkdir -p build/omhome outputs/matlab outputs/config outputs/data outputs/topology outputs/examples vendor

python3 scripts/validate_commands.py \
  --catalog config/ecms_command_catalog.csv \
  --commands examples/bfp_trip_commands.csv
if [[ "$command_scenario" == "bfp_trip" ]]; then
  python3 scripts/validate_commands.py \
    --catalog config/ecms_command_catalog.csv \
    --commands examples/bfp_trip_commands.csv \
    --stop-time "$stop_time_s"
fi

python3 scripts/render_modelica.py \
  --trip-time "$trip_time_s" \
  --trip-ramp-duration "$trip_ramp_duration_s" \
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

# A run owns these generated paths. Remove prior results only after all cheap
# input checks pass, so an invalid request cannot erase the last good bundle.
rm -f "$project_root/build/thermosyspro_trip_tac_res.csv"
rm -rf "$project_root/outputs"
mkdir -p outputs/matlab outputs/config outputs/data outputs/topology outputs/examples

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

python3 scripts/normalize_processbus.py \
  --input outputs/thermosyspro-raw.csv \
  --output outputs/processbus.csv \
  --mapping-review outputs/signal-mapping-review.json \
  --trip-time "$trip_time_s"

python3 scripts/generate_ecms.py \
  --processbus outputs/processbus.csv \
  --a-settings config/ecms_a_settings.csv \
  --a-equipment config/ecms_a_equipment.csv \
  --m-links data/ecms_m_links.csv \
  --m-tags data/thermo_vpp_m_locked_tags.csv \
  --fault-preset "$fault_preset" \
  --trip-time "$trip_time_s" \
  --sampling-profile "$sampling_profile" \
  --incident-period-ms "$incident_period_ms" \
  --incident-pre-ms "$incident_pre_ms" \
  --incident-post-ms "$incident_post_ms" \
  --trend-output outputs/ecms-trend.csv \
  --event-output outputs/ecms-events.csv \
  --feeder-output outputs/ecms-feeders.csv \
  "${command_args[@]}"

cp topology/triplens_ecms_vpp.svg outputs/topology/triplens_ecms_vpp.svg
cp topology/triplens_ecms_6p9kv.svg outputs/topology/triplens_ecms_6p9kv.svg
cp data/ecms_m_links.csv outputs/data/ecms_m_links.csv
cp data/ecms_tag_catalog.csv outputs/data/ecms_tag_catalog.csv
cp data/thermo_vpp_m_locked_tags.csv outputs/data/thermo_vpp_m_locked_tags.csv
cp data/m_layer_manifest.json outputs/data/m_layer_manifest.json
cp config/ecms_a_settings.csv outputs/config/ecms_a_settings.csv
cp config/ecms_a_equipment.csv outputs/config/ecms_a_equipment.csv
cp config/ecms_command_catalog.csv outputs/config/ecms_command_catalog.csv
cp config/fault_presets.json outputs/config/fault_presets.json
cp config/signal_map.json outputs/config/signal_map.json
cp examples/bfp_trip_commands.csv outputs/examples/bfp_trip_commands.csv
cp matlab/triplens_ecms_editor.m outputs/matlab/triplens_ecms_editor.m
cp matlab/triplens_ecms_vpp_editor.m outputs/matlab/triplens_ecms_vpp_editor.m
cp matlab/triplens_ecms_vpp_simulate.m outputs/matlab/triplens_ecms_vpp_simulate.m
cp matlab/run_cloud_result.m outputs/matlab/run_cloud_result.m
cp ECMSVPP.m outputs/ECMSVPP.m
cp ECMS_START.m outputs/ECMS_START.m
cp ECMS_RUN.m outputs/ECMS_RUN.m
cp ECMS_RESULT.m outputs/ECMS_RESULT.m
cp ECMS_DIAGNOSE.m outputs/ECMS_DIAGNOSE.m
cp ECMS_SELF_TEST.m outputs/ECMS_SELF_TEST.m

python3 scripts/build_manifest.py \
  --output-dir outputs \
  --trip-time "$trip_time_s" \
  --trip-ramp-duration "$trip_ramp_duration_s" \
  --stop-time "$stop_time_s" \
  --sampling-profile "$sampling_profile" \
  --output-intervals "$intervals" \
  --incident-period-ms "$incident_period_ms" \
  --incident-pre-ms "$incident_pre_ms" \
  --incident-post-ms "$incident_post_ms" \
  --requested-trip-time "$requested_trip_time_s" \
  --requested-trip-ramp-duration "$requested_trip_ramp_duration_s" \
  --requested-stop-time "$requested_stop_time_s" \
  --requested-output-intervals "$requested_intervals" \
  --fault-preset "$fault_preset" \
  --command-scenario "$command_scenario" \
  --thermosyspro-commit "$thermosyspro_commit" \
  --openmodelica-image "$openmodelica_image"

python3 scripts/validate_outputs.py \
  --output-dir outputs \
  --trip-time "$trip_time_s" \
  --sampling-profile "$sampling_profile"
