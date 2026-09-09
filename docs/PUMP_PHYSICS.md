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
5. the spring-loaded discharge check valve's flap and hydraulic resistance
   move continuously to the closed position before sustained reverse flow;
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
scripts/run_pump_physics_pipeline.sh FWP-HP 300 305 3050
scripts/run_pump_physics_pipeline.sh FWP-IP 300 308 3080
scripts/run_pump_physics_pipeline.sh FWP-LP 300 315 3150
scripts/run_pump_physics_pipeline.sh COND-PUMP 300 315 3150
scripts/run_pump_physics_pipeline.sh CW-PUMP 300 308 3080
```

The output sampling interval is 0.1 s in these examples. Each stop time captures
breaker opening, coastdown, check-valve closure, and the first downstream
process response without extrapolating a full-plant shutdown beyond the pinned
example's valid transient envelope. DASSL still takes smaller internal
integration steps around the transient.
