# TripLens repository map

## Active repositories

| Repository | Role | ThermoSysPro relationship | Use it for |
| --- | --- | --- | --- |
| [`khaku25/triplens-thermosyspro-cloud-runner`](https://github.com/khaku25/triplens-thermosyspro-cloud-runner) | Primary physical-model and data pipeline | `main` pins ThermoSysPro 3.1 commit `db81ae1b5a6a85f6c6c7693244cafa6087e18ff5`; HPBP/LPBP is patched into `CombinedCycle_TripTAC` | OpenModelica RAW generation, physical trip and bypass validation, ProcessBus conversion, alarms, SOE, and the packaged MATLAB ECMS project |
| [`khaku25/triplens-matlab-cosim-runner`](https://github.com/khaku25/triplens-matlab-cosim-runner) | MATLAB/ECMS live co-simulation bridge | Consumes the physical model/FMU contract rather than owning the full ThermoSysPro source | MATLAB Online, OPC UA/TCP exchange, FMU stepping, and live ECMS integration |

## Experimental branch

ThermoSysPro 4.2 compatibility work is isolated on
[`codex/thermosyspro-42-init-diagnostic-20260910`](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/tree/codex/thermosyspro-42-init-diagnostic-20260910).
Its lightweight HP/LP bypass acceptance test passes, but the long, fully integrated
4.2 plant transient is not the production ECMS path.

## Empty placeholders

| Repository | Status |
| --- | --- |
| `khaku25/triplens-thermosyspro-cloud` | Empty private placeholder; not an executable runner |
| `khaku25/vvp` | Empty legacy placeholder; not part of the active stack |

## Version rule

Do not infer the ThermoSysPro library version from an ECMS ZIP or UI version.
The physical version is determined by the pinned ThermoSysPro commit and the
`version` field in `ThermoSysPro/package.mo`.
