# TripLens master-to-draw.io synchronisation

User-approved scope: edit the existing 06 Tag Master and 07 Logic Master once, then regenerate 08 links, 09 diagram definition, 10 input/equipment groups, one editable draw.io repository, a tag/rule index, and the web logic detail. Preserve draw.io positions and dimensions using stable semantic IDs. No OPC UA write, protection/runtime/Modelica modification, or automatic promotion of behavioural verification.

## Authority
06/07 are authoring sources. 08/09/10 are derived views, not independent editors. Existing cell text and source status are preserved; cached ports are rebuilt against source identities. Live eligibility is checked against the supplied census, not the typed word PASS. Unknown inputs, duplicate identifiers, mismatching groups, undeclared local outputs and invalid XML/geometry block publication.

## Output
An uncompressed .drawio file holds rule, shared-input and equipment pages. Metadata records exact tag/rule IDs, condition, delay, reset/hysteresis and verification scope. Numeric delay becomes a delay element; textual runtime descriptions remain annotations. Hysteresis is a comparator property, not an invented downstream operation. Runtime interfaces remain explicit opaque blocks with listed outputs, not invented internal chains.

A generated index supports tag → rule → diagram and diagram → tag. The first-party viewer reads the same .drawio file and its geometry; it does not depend on accessing diagrams.net. It supports generated rectangular logic blocks, orthogonal lines, scrolling/zooming, full-page fit, native/derived labels and exact-tag links. Arbitrary draw.io custom shapes are outside this renderer's supported subset.

## Synchronisation and safety
Build every output in staging, validate, then publish. Stable IDs preserve diagram geometry, edge waypoints and approved visual styles. Master changes win over manually edited semantic labels. Schema and checksum identify a release; old output remains intact after validation failure. Layout changes can be imported from compressed or uncompressed draw.io. New tags require an updated live census; changing a description does not.

GitHub manual workflow imports 06/07 from the configured Drive IDs and generates versioned outputs; checked-in snapshots support reproducible offline builds. Windows wrapper performs the same update. Drive-write automation requires an explicitly configured Drive credential; the ChatGPT connector is not a credential for Actions. Current-session copies are saved through the authorised Drive connector. Production deployment is reported separately from code/test completion.
