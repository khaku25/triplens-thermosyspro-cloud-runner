#!/usr/bin/env bash
set -euo pipefail

# Compatibility entry point for the historical HP-BFP workflow. The physical
# implementation now lives in the all-pump runner and no longer prescribes a
# residual shaft speed.

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
cd "$project_root"

event_time_s="${1:-10}"
transition_duration_s="${2:-5}"
stop_time_s="${3:-70}"
intervals="${4:-700}"
final_rpm="${5:-1000}"

echo "Deprecated inputs retained for CLI compatibility: transition=${transition_duration_s}s final_rpm=$final_rpm"
chmod +x scripts/run_pump_physics_pipeline.sh
scripts/run_pump_physics_pipeline.sh FWP-HP "$event_time_s" "$stop_time_s" "$intervals"

mkdir -p outputs
cp outputs/pumps/fwp_hp/thermosyspro-raw.csv outputs/thermosyspro-raw.csv
cp outputs/pumps/fwp_hp/raw-manifest.json outputs/raw-manifest.json

python3 scripts/validate_raw_outputs.py --output-dir outputs
