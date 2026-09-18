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