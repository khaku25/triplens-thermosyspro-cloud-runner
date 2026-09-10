#!/usr/bin/env bash
set -euo pipefail

# One command owns the complete commissioning proof:
#   OpenModelica RAW -> ProcessBus -> DCS1/DCS2/ECMS -> exact-value dashboard.
# The native RAW runner remains independently fail-closed and RAW-only.

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
cd "$project_root"

profile="${1:-gt_trip_commissioning_1ms}"
case "$profile" in
  gt_trip_commissioning_1ms)
    event_time_s=2
    ecms_sampling_profile=incident_1ms
    ;;
  gt_trip_full_100ms)
    event_time_s=300
    ecms_sampling_profile=causal_100ms
    ;;
  *)
    echo "physical handoff accepts only gt_trip_commissioning_1ms or gt_trip_full_100ms" >&2
    exit 2
    ;;
esac

chmod +x scripts/run_pipeline.sh
scripts/run_pipeline.sh 600 5 1000 1000 "$profile"

raw_path="$project_root/outputs/thermosyspro-raw.csv"
raw_hash_before="$(sha256sum "$raw_path" | cut -d' ' -f1)"

python3 scripts/vpp_alarm_engine.py \
  --raw "$raw_path" \
  --input-kind raw \
  --event-time "$event_time_s" \
  --output-dir "$project_root/outputs/integration" \
  --ecms-sampling-profile "$ecms_sampling_profile" \
  --physical-source-policy require-observed \
  --physical-handoff

raw_hash_after="$(sha256sum "$raw_path" | cut -d' ' -f1)"
if [[ "$raw_hash_before" != "$raw_hash_after" ]]; then
  echo "native OpenModelica RAW changed during the downstream handoff" >&2
  exit 1
fi

python3 - "$project_root/outputs/integration/PHYSICAL-HANDOFF-REPORT.json" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if report.get("status") != "PASS":
    raise SystemExit("physical handoff report did not pass")
if report.get("value_mismatch_count") != 0:
    raise SystemExit("ECMS physical values differ from ProcessBus")
if report.get("max_source_time_offset_ms") != 0:
    raise SystemExit("ECMS source timestamps changed")
print(
    "PHYSICAL_ECMS_GATE_PASS "
    f"rows={report['rows_compared']} signals={report['signals_compared']} "
    f"values={report['values_compared']} mismatch=0 source_time_offset_ms=0"
)
PY

