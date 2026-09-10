# VPP Baseline v1.0

`config/vpp_baseline_v1.json` is the authoritative machine-readable entry point
for the TripLens virtual plant. It freezes the values that had previously been
described as provisional because no real-plant approval data was available.
They are now official **within the VPP**, while remaining explicitly unsuitable
for representing a particular real plant.

## Design basis

| Area | VPP Baseline v1.0 |
|---|---|
| GT/ST reference output | GTG 160 MW, STG 250 MW, combined reference 410 MW |
| Voltage | grid 154 kV, GTG/STG terminal 13.8 kV, auxiliary buses 6.9 kV |
| Speed | GTG/STG 3,600 rpm; FWP-HP/IP/LP 1,400 rpm |
| GT Trip timing | receive 20 ms, 86GT operate after another 35 ms, 52GT open 80 ms from Trip request |
| ST Trip timing | 52ST open 100 ms from resolved ST Trip request |
| Turbine bypass | HPBP: HP main steam→cold reheat; no separate IPBP; LPBP: hot reheat→condenser around IP/LP; no LP-drum dump |
| FWP Trip timing | VCB open 80 ms from Trip command |
| Output decay | GT 0.35 s, ST 0.80 s |
| Speed coastdown time constant | GT 1.20 s, ST 2.50 s |
| 50 element | 8,000 A pickup, 15 ms delay |
| 51 element | 1,200 A pickup, IEC standard inverse, TMS 0.10 |
| Feeder fault model | 12,000 A RMS, 0.20 pu terminal residual voltage |
| Published mass flow | t/h for Tag Master, ProcessBus, alarms/events and GitHub RAW aliases |

The connection points, model-grounded flows, preliminary heat balances and
acceptance gates are recorded in
[`TURBINE_BYPASS_DESIGN_BASIS_V1.md`](TURBINE_BYPASS_DESIGN_BASIS_V1.md).
The bypass topology is locked, but valve `Cv`, spray flow and condenser
acceptance remain explicitly pending OpenModelica transient calibration.

## Alarm contract

All 30 rows in `config/dcs_alarm_rules.csv` are adopted as Baseline v1.0.
Consequently their threshold, direction, hysteresis and delay fields are VPP
design values even though their legacy `status` text correctly says that they
are not plant-approved settings.

Generator active power remains an analog trend and electrical-calculation input.
It has no H/HH/L/LL alarm family; falling MW after a Trip is consequence evidence,
not an alarm or a Trip cause.

This is not a status conflict: `LOCKED` means frozen as a VPP design input;
`PROVISIONAL` or `MODEL_*_NOT_PLANT_APPROVED` in a compatibility CSV describes
its relationship to real-plant evidence. The first controls repeatable virtual
simulation, while the second prevents a false plant-approval claim.

The alarm engine evaluates at 1 ms with zero-order-hold timers, accepts only
GOOD-quality input and emits events only on state transitions. This prevents a
persistent alarm from being repeated at every simulation sample.

All mass-flow thresholds and hysteresis values use `t/h`. Native simulator
connector values are converted once at the publishing boundary by the exact
factor 3.6; alarm logic never compares a t/h threshold with an unconverted
model value.

## Latch and reset contract

- GT and ST latches are set only by their resolved Trip requests.
- FWP Trip immediately sets its latch; a normal STOP neither sets the latch nor
  opens the VCB.
- RESET clears a latch but never closes a breaker. A separate CLOSE command is
  required after permissives are satisfied.
- Falling MW, RPM, flow or pressure is an effect and cannot initiate a Trip
  unless an explicit Baseline rule says so.

## Coupling contract

The eight rows of `config/common_trip_matrix.csv` are part of this Baseline.
Direct GT Trip intertrips ST; direct ST Trip affects ST only. HP/IP/LP drum HH
trips ST, while HP/IP/LP drum LL trips both GT and ST. FWP Trip remains local to
the selected pump feeder.

## Change control

Runtime components should load `config/vpp_baseline_v1.json` first. The CSV
files named under `source_configs` remain tabular execution inputs, and
the Baseline consistency test prevents their operative values from silently
diverging. Any intended design change requires a new Baseline version or an
explicit versioned amendment plus updated tests.
