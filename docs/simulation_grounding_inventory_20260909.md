# TripLens simulation-grounding inventory — 2026-09-09

## Authoritative rule

TripLens executable equipment and logic must be grounded in either:

1. a real ThermoSysPro/OpenModelica model object or solved state/signal, or
2. a real object/state in the ECMS electrical simulation model.

A display convenience, scenario label, derived flow, or boundary signal is not enough to invent a new pump, motor, breaker, relay, or process equipment item.

## Core v1 scope — frozen

The authoritative signal foundation contains two layers, with one explicitly separated common protection layer above them.

### Layer 0 — RAW / model-backed tags

- Values that come from an actual simulation model quantity.
- Thermo process tags are kept only when the catalogue marks them model-backed (`M`) and provides a model mapping.
- ECMS electrical states may remain when they are explicit states of the ECMS simulation topology.

### Layer 1 — first-order state tags

Only a **single RAW model quantity** compared against an **absolute engineering-unit threshold** may create:

- `H`
- `HH`
- `L`
- `LL`

Layer 1 only declares the state. It does not itself contain breaker/relay sequences.

### Layer 2 — common GT/ST protection matrix

The common plant trip relationships are intentionally separated from Layer 1 and are now explicit in `config/common_trip_matrix.csv` and the ECMS Simulink A-logic interface.

- Direct `GT Trip` → `GT Trip request` + `ST Trip request`
- Direct `ST Trip` → `ST Trip request` only
- Any HP/IP/LP Drum `HH` → `ST Trip request` only
- Any HP/IP/LP Drum `LL` → `GT Trip request` + `ST Trip request`

Equivalent equations:

```text
GT_REQ = GT_TRIP_CMD OR HP_LL OR IP_LL OR LP_LL
ST_REQ = ST_TRIP_CMD OR GT_TRIP_CMD OR HP_HH OR IP_HH OR LP_HH OR HP_LL OR IP_LL OR LP_LL
```

`stg_low_state` / low ST MW indication is **not** a Trip source. GT→ST Trip linkage is signal-based, not an indirect consequence of ST output rundown.

Layer 3 actuation remains separate from the matrix: resolved GT request feeds the existing 86GT→52GT path; resolved ST request feeds the 52ST trip latch. The current breaker timing values are virtual-model provisional values, not plant-approved C&E settings.

### Deferred beyond the common matrix

The following remain outside the current validated common protection scope unless separately model-grounded and tested:

- other Master Trip / Unit Trip / ESD causes
- additional 86/lockout schemes not present in the current model
- permissives / interlocks beyond the implemented trip paths
- automatic bus transfer sequences
- operator event analytics
- communication alarms
- ratio-to-baseline logic
- rate-of-change logic
- multi-signal inferred alarms
- scenario-only sensors
- virtual equipment logic

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

Their START/STOP/TRIP/RESET command rows were also removed from `config/ecms_command_catalog.csv`, and their synthetic `.PHYS` rows were removed from `data/ecms_tag_catalog.csv`.

### Important distinction

- Cooling-water **physics/boundary signals remain** because `SourceCaloporteur`, `PuitsCaloporteur`, and condenser cooling-side quantities are model-grounded.
- Condensate **flow/level signals remain** because condenser and condensate-side solved quantities are model-grounded.
- What was removed is the invented standalone `CW-PUMP` / `COND-PUMP` equipment and command logic.
- `CEP` scenario-only logic in the legacy A-L catalogue is not part of the executable Core.

## Equipment retained pending naming cleanup

The following remain because they correspond to real ThermoSysPro pump objects:

| TripLens current name | Native ThermoSysPro object | Status |
|---|---|---|
| `FWP-HP` | `PompeAlimHP` | KEEP |
| `FWP-IP` | `PompeAlimMP` | KEEP; naming cleanup required |
| `FWP-LP` | `PompeAlimBP` | KEEP; naming cleanup required |

Naming normalization (HP/IP/LP vs HP/MP/BP, FWP vs BFP) is deliberately separated from grounding/deletion.

## Legacy catalogue policy

The 903-row legacy A-L CSV remains only as an archive/traceability catalogue. It is not the executable Logic Core.

The current build produces separate Core artifacts:

- `core_model_tags.csv` — Layer 0 model-backed raw tags
- `core_first_order_logic.csv` — Layer 1 H/HH/L/LL rules
- `core_runtime_alarm_rules.csv` — runtime H/HH/L/LL rules

The common trip relationship is maintained separately in `config/common_trip_matrix.csv` so Layer 1 alarm generation and Layer 2 protection action cannot be confused.

Excluded rows are emitted into separate reports so nothing is silently lost.

## ECMS electrical exception

Electrical equipment such as 52GT/52ST, GT/ST main transformers, UAT-A/UAT-B, 6.9 kV incoming breakers and bus tie are retained when they are explicit objects in the ECMS electrical simulation topology. They do not need to be ThermoSysPro process objects, but any higher-order protection/sequence logic must remain explicitly separated from Layer 0/1 and be backed by a reviewed matrix or model state.
