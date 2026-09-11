# Mobile topology PNGs

High-resolution PNG exports of the native OpenModelica–OPC UA SVG diagrams.

| File | Contents | Pixel size |
|---|---|---:|
| `full_process_topology_mobile.png` | Steam/bypass path and all HP/IP/LP FWP discharge check-valve paths in one vertically scrollable image | 2800 x 3160 |
| `steam_path_mobile.png` | HP/IP/LP turbine admission, bypass, spray and condenser paths | 2800 x 1640 |
| `fwp_check_valve_path_mobile.png` | HP/IP/LP feedwater-pump discharge check valves and OPC UA feedback | 2800 x 1520 |
| `opcua_actuator_overview_mobile.png` | ECMS write, native OpenModelica logic and OPC UA feedback overview | 2800 x 1520 |

Regenerate after editing the source SVGs:

```bash
./scripts/render_mobile_topology.sh
```

The PNGs are presentation/viewing exports. The SVG files remain the authoritative diagrams and preserve OPC UA bindings and metadata.
