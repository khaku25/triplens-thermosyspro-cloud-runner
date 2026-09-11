#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output_dir="$repo_root/topology/mobile"
render_width=2800

command -v inkscape >/dev/null 2>&1 || {
  echo "inkscape is required" >&2
  exit 1
}
command -v convert >/dev/null 2>&1 || {
  echo "ImageMagick convert is required" >&2
  exit 1
}

mkdir -p "$output_dir"

inkscape "$repo_root/topology/opcua/opcua_process_wiring.svg" \
  --export-type=png \
  --export-width="$render_width" \
  --export-filename="$output_dir/steam_path_mobile.png"

inkscape "$repo_root/topology/opcua/check_valves/fwp_discharge_check_valve_wiring.svg" \
  --export-type=png \
  --export-width="$render_width" \
  --export-filename="$output_dir/fwp_check_valve_path_mobile.png"

inkscape "$repo_root/topology/opcua/opcua_actuator_overview.svg" \
  --export-type=png \
  --export-width="$render_width" \
  --export-filename="$output_dir/opcua_actuator_overview_mobile.png"

convert \
  "$output_dir/steam_path_mobile.png" \
  "$output_dir/fwp_check_valve_path_mobile.png" \
  -background '#07111f' \
  -append \
  -strip \
  -define png:compression-level=9 \
  "$output_dir/full_process_topology_mobile.png"

identify \
  "$output_dir/full_process_topology_mobile.png" \
  "$output_dir/steam_path_mobile.png" \
  "$output_dir/fwp_check_valve_path_mobile.png" \
  "$output_dir/opcua_actuator_overview_mobile.png"
