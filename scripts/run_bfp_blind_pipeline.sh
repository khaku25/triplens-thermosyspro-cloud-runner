#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
cd "$project_root"

bfp_trip_time_s="${1:-600}"
bfp_coastdown_duration_s="${2:-5}"
stop_time_s="${3:-1000}"
intervals="${4:-1000}"
bfp_final_rpm="${5:-1000}"

openmodelica_image="openmodelica/openmodelica:v1.27.0-minimal"
thermosyspro_commit="db81ae1b5a6a85f6c6c7693244cafa6087e18ff5"

python3 scripts/render_bfp_modelica.py \
  --trip-time "$bfp_trip_time_s" \
  --coastdown-duration "$bfp_coastdown_duration_s" \
  --stop-time "$stop_time_s" \
  --intervals "$intervals" \
  --final-rpm "$bfp_final_rpm"

mkdir -p build/omhome vendor
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

# These paths are owned by this generated scenario only.
rm -f "$project_root/build/thermosyspro_bfp_blind_res.csv"
rm -rf "$project_root/bfp-outputs"
mkdir -p bfp-outputs/engineering bfp-outputs/blind-input bfp-outputs/ground-truth

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
  omc /workspace/build/run_bfp.mos

if [[ ! -s build/thermosyspro_bfp_blind_res.csv ]]; then
  echo "OpenModelica did not create a fresh BFP result" >&2
  exit 1
fi
cp build/thermosyspro_bfp_blind_res.csv bfp-outputs/engineering/thermosyspro-bfp-raw.csv

python3 scripts/normalize_bfp_processbus.py \
  --input bfp-outputs/engineering/thermosyspro-bfp-raw.csv \
  --output bfp-outputs/engineering/processbus-bfp.csv \
  --review bfp-outputs/engineering/signal-mapping-review.json

python3 scripts/generate_bfp_blind.py \
  --processbus bfp-outputs/engineering/processbus-bfp.csv \
  --trip-time "$bfp_trip_time_s" \
  --stop-time "$stop_time_s" \
  --final-rpm "$bfp_final_rpm" \
  --output-dir bfp-outputs

python3 scripts/validate_bfp_blind.py \
  --output-dir bfp-outputs \
  --trip-time "$bfp_trip_time_s" \
  --stop-time "$stop_time_s" \
  --final-rpm "$bfp_final_rpm"
