# Plant Process View · Drawing Master v36

## Source and scope

- Visual source: uploaded `TripLens_CombinedCycle_TripTAC_ProcessView_v36(2).mo` Diagram annotation, SHA-256 `6d27dbd43efaf778859bcf26a88265e57323db565a791735c261e2dab03355da`.
- Web background: its 2044 × 1285 captured Process View at `apps/web/public/drawing/plant-process-v36.png`. The web background is a static snapshot; its numeric values are **not** live.
- Coordinate frame: `{{-240,-165},{240,140}}`, with upward positive Y. `plantHotspots.mjs` converts source symbol bounds to percentages in the rendered image.
- Existing ECMS sources: `topology/triplens_ecms_vpp.svg` and `topology/triplens_ecms_6p9kv.svg`, copied unchanged into public assets. ECMS overview bus areas lead to the 6.9 kV detail.
- Modelica `equation`, `connect()`, simulation settings and OPC UA publication are outside this web change.

## Hotspot mapping

The registry contains 19 symbols. Coordinates below are source annotation bounds, expressed as `x-min, y-min, x-max, y-max`.

| Object | Bounds | Object | Bounds |
| --- | --- | --- | --- |
| GT | -220,18,-204,35 | GTG | -195,18,-179,35 |
| HP_DRUM | -126,-101,-94,-67 | IP_DRUM | 27,-101,59,-67 |
| LP_DRUM | 196,-110,228,-67 | HP_TURBINE | -76,58,-44,90 |
| IP_TURBINE | 116,58,148,90 | LP_TURBINE | 186,58,218,90 |
| HP_BYPASS_VLV | -112,22,-86,42 | LP_BYPASS_VLV | 76,22,102,42 |
| HP_SPRAY | -74,22,-48,42 | LP_SPRAY | 114,22,140,42 |
| HP_BFP | -194,-88,-170,-64 | IP_BFP | -41,-88,-17,-64 |
| LP_BFP | 140,-88,164,-64 | HP_BFP_NRV | -158,-85,-146,-67 |
| IP_BFP_NRV | -5,-85,7,-67 | LP_BFP_NRV | 174,-85,186,-67 |
| CONDENSER | 180,-48,228,-10 | | |

HP/IP/LP drums are highlighted at the feedwater and level vessels in the lower row. The v36 screenshot contains no standalone ST generator symbol, so STG/52ST remain in ECMS. No invented Plant object is registered.

## EVENT navigation and limitations

`equipmentMaster.mjs` resolves explicit names to `equipment_id`, `plant_location_id` and `ecms_location_id`. It uses the existing `FWP-HP/IP/LP` identifiers and explicitly maps the operator names HP/IP/LP BFP to those pumps. Unknown names have no inferred location or misleading link. EVENT timeline and table links open `/drawing?equipment=...` in another tab to preserve the active analysis. A view parameter can request the electrical location for a pump, e.g. `/drawing?equipment=LP%20BFP&view=ecms` highlights VCB-A02.

RAW and OPC UA value overlays are a separate phase. The image labels show the capture time only; do not interpret the displayed zero values as the uploaded EVENT/RAW measurement.

## Verification

- `node --test tests/test_plant_drawing.mjs`: registry and exact mapping.
- `node --test tests/browser_plant_drawing.mjs` after `npm run build` with Playwright installed: desktop direct jumps, ECMS bus drill down, VCB jump and mobile focus. The browser test starts a production server itself.
- `python -m unittest tests.test_drawing_master tests.test_logic_pipeline`: original Drawing Master contract.
