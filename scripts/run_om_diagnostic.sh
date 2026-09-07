#!/usr/bin/env bash
set -euo pipefail

variant="${1:?diagnostic variant is required}"
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

openmodelica_image="openmodelica/openmodelica:v1.27.0-minimal"
thermosyspro_commit="db81ae1b5a6a85f6c6c7693244cafa6087e18ff5"
model_name="TripLens_Diagnostic"

mkdir -p "build/diagnostics/$variant/omhome" vendor

if [[ ! -e vendor/ThermoSysPro ]]; then
  git clone --no-checkout https://github.com/Dwarf-Planet-Project/ThermoSysPro.git vendor/ThermoSysPro
fi
git -C vendor/ThermoSysPro checkout --detach "$thermosyspro_commit"

case "$variant" in
  original)
    model_name="ThermoSysPro.Examples.CombinedCyclePowerPlant.CombinedCycle_TripTAC"
    ;;
  steady)
    flow_table='[0,606.94; 1000,606.94]'
    temperature_table='[0,893.75; 1000,893.75]'
    ;;
  ramp_60)
    flow_table='[0,606.94; 600,606.94; 660,50; 1000,50]'
    temperature_table='[0,893.75; 600,893.75; 660,423; 1000,423]'
    ;;
  ramp_300)
    flow_table='[0,606.94; 600,606.94; 900,50; 1000,50]'
    temperature_table='[0,893.75; 600,893.75; 900,423; 1000,423]'
    ;;
  *)
    echo "unknown diagnostic variant: $variant" >&2
    exit 2
    ;;
esac

if [[ "$variant" != "original" ]]; then
  sed \
    -e "s|@FLOW_TABLE@|$flow_table|" \
    -e "s|@TEMPERATURE_TABLE@|$temperature_table|" \
    modelica/TripLens_Diagnostic.mo.tpl \
    > "build/diagnostics/$variant/TripLens_Diagnostic.mo"
fi

load_diagnostic=''
if [[ "$variant" != "original" ]]; then
  load_diagnostic='loadFile("/workspace/build/diagnostics/'"$variant"'/TripLens_Diagnostic.mo"); getErrorString();'
fi

sed \
  -e "s|@LOAD_DIAGNOSTIC@|$load_diagnostic|" \
  -e "s|@MODEL_NAME@|$model_name|g" \
  -e "s|@VARIANT@|$variant|g" \
  -e "s|@PREFIX@|diagnostic_$variant|g" \
  modelica/diagnostic.mos.tpl \
  > "build/diagnostics/$variant/run.mos"

docker run --rm \
  -v "$project_root/build/diagnostics/$variant/omhome:/root" \
  -v "$project_root:/workspace" \
  -w /workspace \
  "$openmodelica_image" \
  omc /workspace/modelica/install_dependencies.mos

set +e
docker run --rm \
  -v "$project_root/build/diagnostics/$variant/omhome:/root" \
  -v "$project_root:/workspace" \
  -w /workspace \
  "$openmodelica_image" \
  omc "/workspace/build/diagnostics/$variant/run.mos" \
  2>&1 | tee "build/diagnostics/$variant/omc.log"
omc_status=${PIPESTATUS[0]}
set -e

python3 scripts/check_diagnostic_result.py \
  --csv "build/diagnostics/$variant/diagnostic_${variant}_res.csv" \
  --expected-stop-time 1000 \
  --variant "$variant" \
  --omc-status "$omc_status" \
  --summary "build/diagnostics/$variant/summary.json"
