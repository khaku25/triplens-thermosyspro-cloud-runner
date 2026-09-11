# Native OpenModelica OPC UA visual contract v1

This document defines the SVG scope for the current TripLens native OPC UA
runtime. The runtime path is:

`ECMS / MATLAB ⇄ OPC UA TCP ⇄ native OpenModelica ThermoSysPro`

The visual assets use only the native OPC UA interface.

## Addressing rule

OpenModelica registers model-variable nodes dynamically. Applications therefore
resolve those variables by exact OPC UA `BrowseName`, matching
`scripts/native_ecms_opcua_client.py`. A numeric NodeId must not be invented or
hard-coded for a model variable.

The two supported namespace-0 solver-control nodes are the exception:

| Purpose | NodeId | BrowseName | Application access |
|---|---|---|---|
| Advance one communication step | `ns=0;i=10000` | `OpenModelica.step` | Write |
| Read solved simulation time | `ns=0;i=10004` | `OpenModelica.time` | Read |

The default local endpoint is `opc.tcp://127.0.0.1:4841`.

## Command and actuator scope

The current physical contract has one ECMS write:

| BrowseName | Type | Meaning |
|---|---|---|
| `vppExternalTripCommandNative` | Double 0/1 | Derived GT Trip request written once on its rising edge |

That request resolves `vppSTTripLatch` inside the Modelica model. The latch then
closes the HP/IP turbine admission and LP-drum admission paths, opens HPBP/LPBP,
and enables both spray paths. The seven actuator groups are visible over OPC UA,
but they do not yet have independent write nodes. Their position and flow nodes
are application-read-only.

`HP_SPRAY_VLV` and `LP_SPRAY_VLV` are operator-facing names. In the current
ThermoSysPro implementation each is a controlled mass-flow source plus an
injector, not a native valve body; the SVGs state this explicitly.

## Generated assets

- `topology/opcua/opcua_actuator_overview.svg`: command, solver and feedback overview.
- `topology/opcua/opcua_process_wiring.svg`: complete implemented admission,
  bypass, spray and condenser process paths.
- `topology/opcua/valves/*.svg`: seven equipment-detail drawings.
- `topology/opcua/opcua_svg_manifest.json`: machine-readable asset and node map.

Generate or verify them with:

```bash
python3 scripts/generate_opcua_svg_assets.py
python3 scripts/generate_opcua_svg_assets.py --check
python3 -m unittest tests.test_opcua_svg_assets -v
```

These drawings are a simulation/communication contract. They are not operating,
isolation, safety, or LOTO drawings.
