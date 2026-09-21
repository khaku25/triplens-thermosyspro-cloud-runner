# Recovery Readiness — Implementation Handoff

Status: **isolated implementation branch / not merged**

Branch: `codex/recovery-readiness-ui`

Purpose: add a read-only, model-derived **GT / ST Ready-to-Start** view to the TripLens recovery workspace without changing Modelica, OPC UA, Gemini, or Drawing Master.

## 1. Design boundary

This feature does **not** claim to reproduce a plant-approved APS sequence.

It derives a deterministic readiness view from signals and rules already present in the Current V8 package. It must remain:

- read-only;
- deterministic;
- fail-closed on missing required data;
- independent of Gemini text generation;
- independent of new OPC UA nodes;
- independent of Modelica changes;
- independent of Drawing Master.

No RESET, START, BREAKER CLOSE, valve, or other plant-control action may be exposed.

## 2. Readiness hierarchy

```text
HRSG PROTECTION ─┐
                 ├─> BOP / HRSG READY TO START ─┬─> GT READY TO START
FEEDWATER ───────┘                               └─> ST READY TO START

GT START PERMISSIVES ───────────────────────────────> GT READY TO START
ST START PERMISSIVES ───────────────────────────────> ST READY TO START
```

Logical relationship:

```text
BOP_HRSG_READY = HRSG_PROTECTION AND FEEDWATER

GT_READY_TO_START = GT_START_PERMISSIVES AND BOP_HRSG_READY
ST_READY_TO_START = ST_START_PERMISSIVES AND BOP_HRSG_READY
```

A BOP/HRSG blocker therefore propagates to both GT and ST readiness. A train-local blocker propagates only to that train.

## 3. Current V8 leaf contract

The implementation uses only tags already present in `data/current_v8/live_tag_master.csv` and rule IDs already present in `data/current_v8/live_logic_runtime.csv`.

### GT START PERMISSIVES

- `vppGTTripLatch` → clear → `PROT-GT-LATCH`
- `vppGTTripRequest` → clear → `PROT-GT-REQUEST`
- `vpp52GTClosed` → open during recovery isolation → `SEQ-52GT-OPEN`

### ST START PERMISSIVES

- `vppSTTripLatchPublished` → clear → `PROT-ST-LATCH`
- `vppSTTripRequest` → clear → `PROT-ST-REQUEST`
- `vpp52STClosed` → open during recovery isolation → `SEQ-52ST-OPEN`

### HRSG PROTECTION

- `vppHPDrumHHRaw` / `vppHPDrumLLRaw`
- `vppIPDrumHHRaw` / `vppIPDrumLLRaw`
- `vppLPDrumHHRaw` / `vppLPDrumLLRaw`

All six must be clear in this model-derived readiness layer.

### FEEDWATER

- `vppHPFWPTripLatchNative`
- `vppIPFWPTripLatchNative`
- `vppLPFWPTripLatchNative`

All three must be clear for the shared BOP/HRSG readiness node.

## 4. Runtime semantics

Each leaf has exactly three display states:

- `SATISFIED`: required value is present and matches the readiness condition.
- `BLOCKED`: required value is present and blocks readiness.
- `DATA_MISSING`: required input cannot be resolved or interpreted.

Aggregation is fail-closed:

1. any `BLOCKED` → parent `BLOCKED`;
2. else any `DATA_MISSING` → parent `DATA_MISSING`;
3. else parent `SATISFIED`.

The latest non-empty RAW sample is used. Existing `raw__...` prefixed columns are accepted by suffix matching. No new source tag is generated.

## 5. UI target

Recovery workspace order:

1. **GT / ST 재기동 준비상태**
2. GT READY TO START / ST READY TO START summary cards
3. shared **BOP / HRSG READY TO START**
4. leaf groups and blocking conditions
5. existing **실제 복구 기록** form

A leaf can disclose:

- resolved source tag;
- current value;
- model time;
- registered logic ID;
- affected train(s).

The UI must not contain operator control buttons.

## 6. Required acceptance cases

Before merge, the following must pass against the final stabilized base:

1. all leaf inputs clear → GT READY + ST READY;
2. LP BFP trip latch active → FEEDWATER BLOCKED → BOP/HRSG BLOCKED → GT + ST BLOCKED;
3. GT-local blocker → GT BLOCKED only while shared prerequisites remain ready;
4. one shared HRSG input missing → BOP/HRSG DATA_MISSING → GT + ST DATA_MISSING;
5. `raw__` prefixed source columns resolve without OPC UA changes;
6. latest non-empty sample controls the displayed state;
7. current V8 tag/rule contract test confirms every leaf exists;
8. existing recovery form, report export, evidence drawer, mobile layout, and upload reset behavior remain unchanged.

## 7. Stabilized-base integration procedure

Do **not** merge this branch while rollback/stabilization is still moving the production base.

After the other stabilization work declares one final stable SHA:

1. record that SHA as the integration base;
2. create a fresh integration branch from that exact SHA;
3. transplant only the Recovery Readiness files/diffs;
4. resolve the three expected shared-file touch points:
   - `apps/web/components/TripLensWorkspace.js`
   - `apps/web/lib/contracts.js`
   - `apps/web/app/integration.css`
5. run readiness unit/contract tests;
6. run the repository's existing UI/report/recovery tests;
7. run one real EVENT+RAW E2E case;
8. verify LP BFP case propagation to both GT and ST readiness;
9. verify mobile layout;
10. only then open/merge the final PR.

## 8. Files owned by this feature

Primary isolated files:

- `apps/web/lib/recoveryReadiness.mjs`
- `apps/web/components/RecoveryReadiness.js`
- `tests/test_recovery_readiness.mjs`
- `tests/test_recovery_readiness_ui.mjs`
- `tests/test_recovery_readiness_source_contract.mjs`

Shared integration files:

- `apps/web/components/TripLensWorkspace.js`
- `apps/web/lib/contracts.js`
- `apps/web/app/integration.css`

This separation is intentional so the feature can be rebased/transplanted after production rollback without dragging unrelated branch history into the stabilized release.
