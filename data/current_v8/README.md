# Current V8 Live SOT

This directory is the machine-readable runtime baseline for TripLens.

- Validation evidence: GitHub Actions #54 / run `35309650110`
- Live OPC UA `vpp*` BrowseNames: 603
- Current Logic Master: 53 rules
- Unique live logic inputs: 44
- Unique live `vpp*` logic outputs: 28
- Writable current inputs: 66
- Valve/breaker persistence proof: 56/56

`live_tag_allowlist.csv` contains only source identities observed in the running OpenModelica OPC UA server.
`live_logic_runtime.csv` contains only Current Logic rows whose source inputs and `vpp*` outputs resolve against that live set.
TripLens-local derived alarm IDs are valid rule outputs but are not OPC UA source nodes.

The authoring masters and static web viewer also keep two later ST MW observations
and `RESP-ST-GRID-POWER` in separate model-source sheets. They are searchable and
linked in the logic diagram, but are not part of the Run 54 census or live runtime.
The supplied RAW session contains 282 rows with 52ST closed and no open-breaker
rows; the 52ST OPEN behavior remains `NOT_TESTED`, and the response remains `PARTIAL`.
