# VPP Turbine Bypass Design Basis v1

Status: **topology locked; physical implementation and Cv calibration pending**
Scope: public virtual-plant design, not plant-approved operating data

## 1. Locked topology

The virtual plant uses two turbine-bypass systems.

| System | Installed | Source | Destination | Function |
|---|---:|---|---|---|
| HPBP | Yes | HP main-steam header, upstream of HP turbine admission valve | Cold-reheat header, downstream of HP turbine | Bypass HP turbine |
| IPBP | No | — | — | Separate IP bypass is intentionally omitted |
| LPBP | Yes | Hot-reheat header, upstream of IP turbine admission valve | Condenser steam-inlet header | Bypass both IP and LP turbines |
| LP drum steam dump | No | — | — | Separate dump system is outside this VPP design |

ThermoSysPro native names map as `HP=HP`, `MP=IP`, and `BP=LP`. Therefore,
the LPBP source is on the `MP` turbine inlet/hot-reheat header. It is not a
branch from `BallonBP`, `vanne_vapeurBP`, or the LP drum steam line.

The corresponding topology drawing is
[`topology/turbine_bypass_vpp.svg`](../topology/turbine_bypass_vpp.svg).

## 2. Current-model connection points

The inherited `CombinedCycle_TripTAC` model has no turbine bypass branch. Its
HP and IP turbine admission valves are held at constant 0.8 opening and are not
connected to the Trip latch. The following inherited fluid nodes are the
intended branch points for the VPP extension.

| New branch | Take-off node | Discharge node | Existing valve isolated on ST Trip |
|---|---|---|---|
| HPBP | `DoubleDebitHP.Cs`, before `vanne_entree_TurbineHP.C1` | HP turbine exhaust/cold-reheat node at `MoitieDebitHP.Ce` | `vanne_entree_TurbineHP` |
| LPBP | `DoubleDebitMP.Cs`, before `vanne_entree_TurbineMP.C1` | Condenser inlet node between `CapteurDebitVapCondenseur.C2` and `Condenseur.Cv` | `vanne_entree_TurbineMP` |
| LP drum isolation | No bypass branch | Existing LP admission path | `vanne_vapeurBP` |

Each bypass train is to contain a pressure-reducing `ControlValve`, spray-water
control valve, `DeheaterMixer2`, flow measurement, and inlet/outlet pressure
and temperature measurements. A small dynamic volume or equivalent numerical
regularization is required at the condenser connection to avoid a zero-flow
algebraic singularity.

## 3. Model-grounded normal point

Values below are read from the verified 1000 s OpenModelica result immediately
before the GT exhaust ramp. They are calibration inputs, not plant settings.

| Quantity | Model value | Design use |
|---|---:|---|
| HP drum pressure | 12.717 MPa | HP pressure consistency check |
| HP main-steam header pressure | about 12.681 MPa | HPBP inlet start value |
| Cold-reheat/HP exhaust pressure | about 2.727 MPa | HPBP outlet start value |
| HP turbine steam flow | 546.1056 t/h | HPBP 100% nominal-flow target |
| IP drum pressure | 2.733 MPa | IP pressure consistency check |
| Hot-reheat/IP inlet pressure | about 2.549 MPa | LPBP inlet start value |
| IP turbine steam flow | 636.3288 t/h | LPBP 100% nominal-flow target |
| LP turbine/condenser steam flow | 707.7384 t/h | Existing condenser normal-flow basis |
| LP drum contribution | 71.4096 t/h | Keep separate from LPBP |
| Condenser pressure | about 6.14 kPa abs | LPBP back-pressure start value |
| ST generator output | about 262.88 MW | Physical-model normal point; baseline rating remains 250 MW pending calibration |

The 250 MW VPP presentation rating and the current physical model's roughly
263 MW normal output are not identical. Bypass heat-balance verification must
use the physical-model value until the generator model is recalibrated.

## 4. Preliminary sizing calculations

### Steam capacity

Both valves initially target 100% of the corresponding pre-Trip turbine flow:

- HPBP: 546.1056 t/h at approximately 12.681 MPa to 2.727 MPa.
- LPBP: 636.3288 t/h at approximately 2.549 MPa to the condenser inlet.

The final `Cvmax` values are deliberately not locked. ThermoSysPro calculates
valve flow from pressure loss, density, valve position, and `Cv`. Steam density
must therefore be solved at the initialized inlet/outlet states in the same
OpenModelica version used by CI, then each valve must be calibrated to its
nominal-flow target.

### Spray-water upper-bound estimate

The initial energy-balance estimate uses

`m_water = m_steam * (h_steam - h_target) / (h_target - h_water)`.

| Train | Assumed states | Preliminary spray flow |
|---|---|---:|
| HPBP | 3.4508 MJ/kg steam; 3.0463 MJ/kg target; 1.3969 MJ/kg spray water | about 133.956 t/h |
| LPBP | 3.5239 MJ/kg steam; 2.7000 MJ/kg target; 0.5500 MJ/kg spray water | about 243.864 t/h |

These are conservative calculation points, not valve settings. The final
values must be recomputed from the simulated pressure/temperature limits and
the actual spray-water take-off state.

### Condenser acceptance

A first-pass energy balance gives approximately 440 MWth for the current normal
condenser load and approximately 620 MWth for full LPBP flow plus the preliminary
spray flow, or about 1.41 times normal duty. Therefore the LPBP cannot be
accepted solely because the mass-flow equation converges. Condenser pressure,
cooling-water duty, hotwell level, and discharge temperature must remain within
the VPP design envelope during the full transient.

## 5. ST Trip command sequence

At `ST_TRIP_LATCH = 1`:

1. Issue HP and IP turbine-admission close commands.
2. Isolate the LP drum steam admission path through `vanne_vapeurBP`.
3. Issue HPBP and LPBP open commands with no intentional delay.
4. Enable both spray-water temperature controls.
5. Open 52ST according to the breaker delay already defined by the VPP baseline.
6. Treat ST MW and RPM decay as results of the Trip, never as initiating causes.

VPP starting values are 150 ms for turbine-admission closure, 300 ms HPBP
stroke, and 400 ms LPBP stroke. Open limit is 95%. Loss-of-air or loss-of-power
fail positions remain pending a failure-mode and condenser-overload review;
they must not be inferred from the normal ST Trip open action.

## 6. Required acceptance checks

- Mass balance at both take-off and discharge nodes, including spray water.
- Energy balance across both desuperheaters.
- No reverse flow into the turbine or HRSG headers.
- HPBP outlet temperature compatible with the cold-reheat/reheater inlet.
- LPBP condenser-inlet temperature and condenser pressure within the VPP envelope.
- Stable hotwell and HP/IP/LP drum levels for 5 s and 120 s observation windows.
- LP drum pressure response after `vanne_vapeurBP` isolation; no implicit drum dump.
- No wide-open bypass while the corresponding turbine admission remains open in normal loaded operation.
- No zero-flow singularity during initialization or after valve closure.
- Event causality: `ST Trip → admission close/bypass open command → valve motion → 52ST open → MW/RPM decay`.
- `VPP_EVENT.csv` contains bypass commands/feedback and drum alarms only when generated by their signals; no answer label is embedded in RAW.

## 7. Tag contract decision

- Publish every mass-flow tag, threshold, event value and GitHub RAW alias in
  `t/h`; the ThermoSysPro connector balance remains internal to the solver and
  is converted by the exact factor 3.6 at the export boundary.
- Keep `TSP.VLV.07.*` for HPBP.
- Remove `TSP.VLV.08.*` IPBP tags.
- Keep `TSP.VLV.09.*`, but define them explicitly as Hot-Reheat LPBP to condenser.
- Keep the LP drum steam/admission valve tags separate from LPBP.
- Keep generator Active Power as an analog measurement; do not create Active
  Power H/HH/L/LL or `POWER_LOW_EVT` alarms.
