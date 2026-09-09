# GT Trip / GT DERATE canonical semantics

## Canonical definitions

- **GT TRIP**: electrical Trip. Success requires `ECMS.52GT.CLOSED=0`.
- **GT DERATE**: exhaust-boundary reduction from `606.94 kg/s / 893.75 K` to `150 kg/s / 550 K` while the GT breaker remains closed.
- The 150/550 boundary must never be presented as proof that GT Trip succeeded.

## Runtime ownership

### True GT Trip

Owned by the VPP/ECMS integrated path:

`GT_TRIP -> 86GT -> 52GT trip command -> ECMS.52GT.CLOSED=0`

The dedicated workflow is `.github/workflows/run-vpp-gt-trip.yml`.

### GT DERATE physical profile

Owned by the ThermoSysPro exhaust-boundary RAW-only runner.

Canonical long profile: `gt_derate_3min_10ms`

The profile changes only the exhaust flow/temperature boundary. It renders the patched model with `--derate-only`, which moves the embedded ThermoSysPro ST Trip trigger past simulation StopTime. Therefore the profile cannot create an ST Trip/bypass sequence merely because the DERATE boundary was applied.

## Legacy identifiers

`TripLens_CombinedCycle_TripTAC` and the renderer options `--trip-time` / `--trip-ramp-duration` are retained as internal compatibility identifiers inherited from the ThermoSysPro source wrapper. They are not TripLens scenario labels and must not be used to classify the 150/550 boundary as GT Trip.

## Regression gate

`tests/test_gt_derate_profile_semantics.py` and `.github/workflows/audit-gt-derate-semantics.yml` fail if:

- `gt_trip_3min_10ms` returns,
- the DERATE renderer asserts the embedded ST Trip trigger during the run,
- the canonical GT Trip command no longer uses breaker feedback,
- or the dedicated VPP GT Trip path disappears.
