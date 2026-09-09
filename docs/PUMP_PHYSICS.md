# TripLens pump physics

The pinned `CombinedCycle_TripTAC` model contains three static centrifugal
pumps: `PompeAlimHP`, `PompeAlimMP`, and `PompeAlimBP`. For each isolated trip,
TripLens retains the selected ThermoSysPro `StaticCentrifugalPump` hydraulic
curve and replaces its prescribed RPM boundary with a dynamic motor-shaft state.
The workflow matrix runs every path; the non-selected pumps retain their proven
upstream steady-state definitions.

Each connected motor pump follows this causal chain:

1. the selected motor feeder breaker changes from closed to open;
2. the connected drive sets electromagnetic motor torque to zero;
3. the combined rotating inertia follows `J*der(w) = motor torque - pump load
   torque - friction torque`;
4. pump head and mass flow change through the native pump curve;
5. the spring-loaded ideal discharge check valve closes before forward flow
   reverses;
6. the existing drum, condenser, valve, economizer, and turbine equations
   calculate the downstream process response.

No residual RPM is prescribed. The former HP-BFP adapter remains only as a
compatibility entry point and delegates to the dynamic runner.

## Physical coverage

| Plant ID | Physical implementation |
|---|---|
| `FWP-HP` | `PompeAlimHP` native curve, dynamic shaft drive, check valve |
| `FWP-IP` | `PompeAlimMP` native curve, dynamic shaft drive, check valve |
| `FWP-LP` | Shared `PompeAlimBP` LP/condensate path |
| `COND-PUMP` | Shared `PompeAlimBP` LP/condensate path |
| `CW-PUMP` | Dynamic inertia/check-valve boundary connected to condenser cooling flow |
| `RECIRC-HP/IP/LP` | Not motor pumps in the pinned base model; retained as natural-circulation paths |

The LP and condensate names are not claimed to be two independent pumps. The
upstream example collapses them into one path. Likewise, the CW example has no
pressure-driven source loop, so TripLens changes its existing mass-flow boundary
without inventing unknown pipe and pump curves. These two simplifications must
be separated only after the plant P&ID and equipment ratings are supplied.

## Run

```bash
scripts/run_pump_physics_pipeline.sh FWP-HP 300 420 4200
scripts/run_pump_physics_pipeline.sh FWP-IP 300 420 4200
scripts/run_pump_physics_pipeline.sh FWP-LP 300 420 4200
scripts/run_pump_physics_pipeline.sh COND-PUMP 300 420 4200
scripts/run_pump_physics_pipeline.sh CW-PUMP 300 420 4200
```

The output sampling interval is 0.1 s in these examples. DASSL still takes
smaller internal integration steps around breaker and valve events.
