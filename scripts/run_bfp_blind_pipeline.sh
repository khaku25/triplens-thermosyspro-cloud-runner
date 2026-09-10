#!/usr/bin/env bash
set -euo pipefail

# This scenario adapter has the same hard boundary as every Action runner:
# publish the native physical CSV only. DCS/ECMS generation belongs downstream.

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
cd "$project_root"

event_time_s="${1:-10}"
transition_duration_s="${2:-5}"
stop_time_s="${3:-70}"
intervals="${4:-700}"
final_rpm="${5:-1000}"

openmodelica_image="openmodelica/openmodelica:v1.27.0-minimal"
thermosyspro_commit="db81ae1b5a6a85f6c6c7693244cafa6087e18ff5"

echo "RAW-only ThermoSysPro run"
echo "Effective physical run: event=${event_time_s}s transition=${transition_duration_s}s stop=${stop_time_s}s intervals=$intervals"

mkdir -p build/omhome vendor

python3 scripts/render_bfp_modelica.py \
  --trip-time "$event_time_s" \
  --coastdown-duration "$transition_duration_s" \
  --stop-time "$stop_time_s" \
  --intervals "$intervals" \
  --final-rpm "$final_rpm"

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

rm -f "$project_root/build/thermosyspro_bfp_blind_res.csv"
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
  omc /workspace/build/run_bfp.mos

if [[ ! -s build/thermosyspro_bfp_blind_res.csv ]]; then
  echo "OpenModelica did not create a fresh non-empty result CSV" >&2
  exit 1
fi

cp build/thermosyspro_bfp_blind_res.csv outputs/thermosyspro-raw.csv
if ! cmp -s build/thermosyspro_bfp_blind_res.csv outputs/thermosyspro-raw.csv; then
  echo "RAW copy differs from the native OpenModelica result" >&2
  exit 1
fi

python3 scripts/build_raw_manifest.py \
  --raw-file outputs/thermosyspro-raw.csv \
  --output outputs/raw-manifest.json \
  --sampling-profile standard \
  --stop-time "$stop_time_s" \
  --output-intervals "$intervals" \
  --thermosyspro-commit "$thermosyspro_commit" \
  --openmodelica-image "$openmodelica_image" \
  --model-variant "FWP_HP_PHYSICAL_TPH_EXPORT_V1"

python3 scripts/validate_raw_outputs.py --output-dir outputs
