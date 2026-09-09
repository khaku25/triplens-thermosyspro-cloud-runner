# TripLens simulation-grounding inventory — 2026-09-09

## Authoritative rule

TripLens executable equipment and logic must be grounded in either:

1. a real ThermoSysPro/OpenModelica model object or solved state/signal, or
2. a real object/state in the ECMS electrical simulation model.

A display convenience, scenario label, derived flow, or boundary signal is not enough to invent a new pump, motor, breaker, relay, or process equipment item.

## ThermoSysPro native-state inspection

Source inspected: native `CombinedCycle_TripTAC` full-state artifact generated from the pinned ThermoSysPro simulation.

- Native CSV columns: 14,755 including `time` → 14,754 model variables.
- Top-level pump objects found: exactly three.
  - `PompeAlimHP`
  - `PompeAlimMP`
  - `PompeAlimBP`
- Drum objects include:
  - `BallonHP`
  - `BallonMP`
  - `BallonBP`
- Condenser/cooling-side objects and signals include:
  - `Condenseur`
  - `CapteurDebitEauCondenseur`
  - `CapteurDebitVapCondenseur`
  - `SourceCaloporteur`
  - `PuitsCaloporteur`
  - `regulation_Niveau_Condenseur`
- Feedwater/turbine valve objects include:
  - `vanne_alimentationHP`
  - `vanne_alimentationMP`
  - `vanne_alimentationBP`
  - `vanne_entree_TurbineHP`
  - `vanne_entree_TurbineMP`
  - `vanne_vapeurHP`
  - `vanne_vapeurMP`
  - `vanne_vapeurBP`

## Deleted synthetic equipment

The following ECMS load/equipment rows were removed because the native ThermoSysPro model has no corresponding standalone pump/motor object and the ECMS model did not provide an independent physical process model for them:

- `RECIRC-HP`
- `RECIRC-IP`
- `RECIRC-LP`
- `COND-PUMP`
- `CW-PUMP`

Their START/STOP/TRIP/RESET command rows were also removed from `config/ecms_command_catalog.csv`.

### Important distinction

- Cooling-water **physics/boundary signals remain** because `SourceCaloporteur`, `PuitsCaloporteur`, and condenser cooling-side quantities are model-grounded.
- Condensate **flow/level signals remain** because condenser and condensate-side solved quantities are model-grounded.
- What was removed is the invented standalone `CW-PUMP` / `COND-PUMP` equipment and command logic.
- `CEP` scenario-only logic in the legacy A-L catalogue is not considered executable model-grounded logic.

## Equipment retained pending naming cleanup

The following remain because they correspond to real ThermoSysPro pump objects:

| TripLens current name | Native ThermoSysPro object | Status |
|---|---|---|
| `FWP-HP` | `PompeAlimHP` | KEEP |
| `FWP-IP` | `PompeAlimMP` | KEEP; naming cleanup required |
| `FWP-LP` | `PompeAlimBP` | KEEP; naming cleanup required |

Naming normalization (HP/IP/LP vs HP/MP/BP, FWP vs BFP) is deliberately separated from grounding/deletion.

## Logic scope policy

The 903-row legacy A-L CSV remains only as an archive/traceability catalogue. The authoritative Logic DB build first excludes non-simulation-grounded rows including:

- `A-L_SCENARIO`
- `A-L_UNLINKED_OPTIONAL`
- `DEMO_SCENARIO_ASSUMED`
- `UNLINKED_CANDIDATE`
- `SCENARIO_ONLY_UNVERIFIED`
- `EXCLUDED_MISSING_INPUT`
- `ABSOLUTE_PHYSICAL_VALUE_NOT_AVAILABLE`
- `DISABLED*` / `EXCLUDED*` implementation states
- deferred scenario sensors/property calculations/level outputs without physical model output

The filtered file is `outputs/simulation_grounded_logic.csv`; excluded rows are reported separately in `outputs/excluded_non_simulation_logic.csv` when CI executes.

## ECMS electrical exception

Electrical equipment such as 52GT/52ST, GT/ST main transformers, UAT-A/UAT-B, 6.9 kV incoming breakers and bus tie are retained when they are explicit objects in the ECMS electrical simulation topology. They do not need to be ThermoSysPro process objects, but their logic must still be driven by ECMS simulation states rather than invented plant events.
