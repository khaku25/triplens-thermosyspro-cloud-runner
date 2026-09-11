# Native OpenModelica solver-health gate

`scripts/check_solver_health.py` checks both the OpenModelica translation log and
the native OPC UA runtime log. It always writes `solver-health.json` before
returning failure for a health finding.

The following findings always fail the gate and cannot be allowlisted:

- division by zero;
- assertion failure or violated min/max assertion;
- linear or nonlinear solver failure;
- compiler/runtime fatal error;
- `NaN` or infinite values;
- a missing input log;
- missing successful-initialization or embedded-server runtime markers.

All other warning lines fail unless they match one reviewed rule in
`config/solver_health_allowlist_v1.json` and remain within that rule's occurrence
budget. The allowlist is intentionally restricted to exact, bounded diagnostics
from the pinned ThermoSysPro 3.1/OpenModelica translation. It contains no runtime
exceptions. A new warning, a changed message, or an increased count therefore
fails closed.

Use this after the native process has stopped:

```bash
python3 scripts/check_solver_health.py \
  --build-log build/native-opcua-build.log \
  --runtime-log outputs/native-opcua/openmodelica-native.log \
  --output outputs/native-opcua/solver-health.json
```

The existing run43 runtime is expected to fail this gate: it contains repeated
division-by-zero diagnostics, solver failures, and violated range assertions.
Passing event-order validation does not override numerical-health failure.
