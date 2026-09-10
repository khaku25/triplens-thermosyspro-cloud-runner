# FMU native valve control contract v1

## Scope

This contract covers exactly the twelve
`ThermoSysPro.WaterSteam.PressureLosses.ControlValve` objects declared by the
pinned `CombinedCycle_TripTAC` model. It does not promote the assumed
`A-CV-01` style catalogue placeholders to physical model objects.

The authoritative inventory is
`config/fmu_valve_control_points_v1.csv`. Generated FMU port and logic
catalogues are:

- `data/fmu_valve_ports_v1.csv`
- `data/fmu_valve_logic_v1.csv`

Regenerate them with:

```bash
python3 scripts/build_fmu_valve_contract.py
python3 scripts/build_fmu_valve_contract.py --check
```

## Command and fault separation

Every valve uses the same signal contract:

```text
CMD = MODE_AUTO ? AUTO_CMD : MAN_CMD
FB  = FAULT_ENABLE ? FAULT_VALUE : CMD
DEVIATION = CMD - FB
```

A manual FMU operation therefore changes `MAN_CMD` and exposes the selected
`CMD`. A stuck or forced-position fault leaves `CMD` intact and changes only
the applied `FB`. This lets TripLens distinguish an operator/controller
closure from a valve that failed away from its command.

Each valve has four FMU inputs:

| Port | Meaning |
|---|---|
| `MODE_AUTO` | select the native automatic driver |
| `MAN_CMD` | external manual opening command |
| `FAULT_ENABLE` | enable a forced-position fault |
| `FAULT_VALUE` | opening applied while the fault is active |

Each valve has eight outputs:

| Port | Meaning |
|---|---|
| `AUTO_CMD` | original controller, constant, ramp or table command |
| `CMD` | selected normal command before fault injection |
| `FB` | opening applied to the ThermoSysPro valve |
| `DEVIATION` | `CMD - FB` |
| `FAULT_ACTIVE` | fault state kept separate from the command |
| `CV` | solved valve coefficient |
| `MASS_FLOW` | solved valve mass flow, published in t/h |
| `DP` | solved inlet-to-outlet pressure difference |

The generated inventory therefore contains 48 inputs, 96 outputs and 144 valve
ports in total.

## Native model limitation

The upstream ThermoSysPro `ControlValve` has no actuator travel state or
independent position transmitter. Its native equation is effectively
`Cv = Ouv.signal * Cvmax`. For v1, `FB` means the opening actually applied to
that physical valve equation. It is not claimed to be an independent plant
position sensor.

To simulate travel time, stiction or a gradual failure later, the Modelica
adapter must add a state between `CMD` and the native `Ouv.signal`. Until the
patched model compiles and runs, adapter-created ports and logic remain marked
`ADAPTER_REQUIRED` or `DESIGN_ONLY_UNTIL_FMU_BUILD`.

## Native valve inventory

| ID | Native object | Original automatic driver |
|---|---|---|
| `HP_FWCV` | `vanne_alimentationHP` | HP drum level controller |
| `HP_STEAM_VLV` | `vanne_vapeurHP` | constant source |
| `IP_FWCV` | `vanne_alimentationMP` | MP/IP drum level controller |
| `IP_STEAM_VLV` | `vanne_vapeurMP` | constant source |
| `LP_STEAM_VLV` | `vanne_vapeurBP` | BP/LP drum level controller |
| `LP_FW_VLV` | `vanne_alimentationBP` | constant source |
| `LP_TO_HPIP_FW_VLV` | `Vanne_alimentationMPHP` | constant source |
| `COND_EXTRACTION_VLV` | `vanne_extraction` | condenser level controller |
| `HP_TURB_ADM_VLV` | `vanne_entree_TurbineHP` | time table |
| `HP_FW_ISO_VLV` | `Vanne_alimentationMPHP1` | time ramp |
| `IP_FW_ISO_VLV` | `Vanne_alimentationMPHP2` | time ramp |
| `IP_TURB_ADM_VLV` | `vanne_entree_TurbineMP` | time table |

Native `MP` and `BP` names are retained in `native_object` and published as
IP and LP only at the TripLens boundary.

## Promotion gate

A valve is not `FMU_CONNECTED` until all of the following pass:

1. the adapter replaces the original `Ouv` driver without double-driving the connector;
2. the unmodified AUTO run matches the baseline within declared tolerances;
3. a MAN command changes the corresponding native `Cv` and mass flow;
4. a fault preserves `CMD` while changing `FB`;
5. OpenModelica builds the FMU and a smoke co-simulation completes;
6. RAW exports include `AUTO_CMD`, `CMD`, `FB`, fault state and physical response.
