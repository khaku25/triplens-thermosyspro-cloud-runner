#!/usr/bin/env bash
set -euo pipefail

# RAW-only ST thermodynamic secondary-effect adapter.
# Canonical Trip success is still 52ST.CLOSED=0 downstream; this Action only
# produces ThermoSysPro process response after HP/MP admission commands close.

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
cd "$project_root"

event_time_s="${1:-10}"
stop_time_s="${2:-70}"
intervals="${3:-700}"

openmodelica_image="openmodelica/openmodelica:v1.27.0-minimal"
thermosyspro_commit="db81ae1b5a6a85f6c6c7693244cafa6087e18ff5"

mkdir -p build/omhome vendor
if [[ ! -e vendor/ThermoSysPro ]]; then
  git clone --no-checkout https://github.com/Dwarf-Planet-Project/ThermoSysPro.git vendor/ThermoSysPro
fi
if ! git -C vendor/ThermoSysPro rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "vendor/ThermoSysPro is incomplete or is not a Git checkout" >&2
  exit 1
fi
git -C vendor/ThermoSysPro checkout --detach "$thermosyspro_commit"
test "$(git -C vendor/ThermoSysPro rev-parse HEAD)" = "$thermosyspro_commit"
test -f vendor/ThermoSysPro/ThermoSysPro/package.mo

python3 scripts/build_st_trip_modelica.py \
  --event-time "$event_time_s" \
  --stop-time "$stop_time_s" \
  --intervals "$intervals"

rm -f build/thermosyspro_st_trip_res.csv
rm -rf outputs
mkdir -p outputs

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
  omc /workspace/build/run_st_trip.mos | tee build/st_trip.log

if [[ ! -s build/thermosyspro_st_trip_res.csv ]]; then
  echo "OpenModelica did not create ST Trip RAW CSV" >&2
  exit 1
fi
grep -q "The simulation finished successfully" build/st_trip.log

cp build/thermosyspro_st_trip_res.csv outputs/thermosyspro-raw.csv
cmp -s build/thermosyspro_st_trip_res.csv outputs/thermosyspro-raw.csv

python3 scripts/build_raw_manifest.py \
  --raw-file outputs/thermosyspro-raw.csv \
  --output outputs/raw-manifest.json \
  --sampling-profile standard \
  --stop-time "$stop_time_s" \
  --output-intervals "$intervals" \
  --thermosyspro-commit "$thermosyspro_commit" \
  --openmodelica-image "$openmodelica_image"
python3 scripts/validate_raw_outputs.py --output-dir outputs

echo "ST_TRIP_RAW_PASS"
echo "TRIP_DEFINITION=52ST.CLOSED=0_DOWNSTREAM"
