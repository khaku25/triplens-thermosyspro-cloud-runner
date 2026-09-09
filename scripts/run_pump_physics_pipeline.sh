#!/usr/bin/env bash
set -euo pipefail

# Native-physics boundary: this runner publishes only OpenModelica RAW and a
# manifest. Alarm and answer-key generation remains downstream.

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
cd "$project_root"

pump_id="${1:-FWP-HP}"
event_time_s="${2:-300}"
stop_time_s="${3:-420}"
intervals="${4:-4200}"

case "$pump_id" in
  FWP-HP|FWP-IP|FWP-LP|COND-PUMP|CW-PUMP) ;;
  *)
    echo "Unsupported physical pump id: $pump_id" >&2
    echo "RECIRC-HP/IP/LP are natural-circulation paths in the pinned base model, not motor pumps." >&2
    exit 2
    ;;
esac

safe_pump_id="$(printf '%s' "$pump_id" | tr '[:upper:]-' '[:lower:]_')"
output_dir="$project_root/outputs/pumps/$safe_pump_id"
result_file="$project_root/build/thermosyspro_pump_${safe_pump_id}_res.csv"

openmodelica_image="openmodelica/openmodelica:v1.27.0-minimal"
thermosyspro_commit="db81ae1b5a6a85f6c6c7693244cafa6087e18ff5"

echo "ThermoSysPro dynamic pump run"
echo "pump=$pump_id event=${event_time_s}s stop=${stop_time_s}s intervals=$intervals"

mkdir -p build/omhome vendor "$output_dir"

if [[ ! -d vendor/ThermoSysPro/.git ]]; then
  if [[ -e vendor/ThermoSysPro ]]; then
    echo "vendor/ThermoSysPro exists but is not a complete Git checkout" >&2
    echo "Remove or relocate that incomplete directory before retrying." >&2
    exit 1
  fi
  git clone --no-checkout https://github.com/Dwarf-Planet-Project/ThermoSysPro.git vendor/ThermoSysPro
fi
if ! git -C vendor/ThermoSysPro rev-parse --show-toplevel >/dev/null 2>&1; then
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

python3 scripts/render_pump_fleet_model.py \
  --pump-id "$pump_id" \
  --trip-time "$event_time_s" \
  --stop-time "$stop_time_s" \
  --intervals "$intervals"

rm -f "$result_file"
rm -f \
  "$output_dir/thermosyspro-raw.csv" \
  "$output_dir/raw-manifest.json"

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
  omc /workspace/build/run_pump_fleet.mos

if [[ ! -s "$result_file" ]]; then
  echo "OpenModelica did not create a fresh non-empty result CSV" >&2
  exit 1
fi

cp "$result_file" "$output_dir/thermosyspro-raw.csv"

python3 scripts/validate_pump_physics.py \
  --input "$output_dir/thermosyspro-raw.csv" \
  --pump-id "$pump_id" \
  --trip-time "$event_time_s"

python3 scripts/build_raw_manifest.py \
  --raw-file "$output_dir/thermosyspro-raw.csv" \
  --output "$output_dir/raw-manifest.json" \
  --sampling-profile standard \
  --stop-time "$stop_time_s" \
  --output-intervals "$intervals" \
  --thermosyspro-commit "$thermosyspro_commit" \
  --openmodelica-image "$openmodelica_image"

python3 scripts/validate_raw_outputs.py --output-dir "$output_dir"

echo "RAW physical output: $output_dir/thermosyspro-raw.csv"
