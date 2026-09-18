# Claim citations and review row identity

Scope: reference integrity of the integrated 119b750 baseline. No plant model, protection matrix, OPC UA write path or original incident data changes.

- The analyzer receives at most one citation-only repair turn, with no additional tool allowance and no Python-invented cause or citation. Candidate records come only from the already retrieved catalog. Failed/insufficient repairs remain UNKNOWN/HOLD; the initial draft remains in audit metadata.
- Literal vpp identifiers in claim text are checked as well as related_tags. Multi-tag RAW intervals require cited endpoints for each sampled tag. Overlapping sample/event intervals are still not exact timing proof.
- Generated report rows carry deterministic row_id metadata. Display numbering is excluded from identity. These IDs are not a ninth CSV column. UI editing preserves IDs.
- The reviewer must return row_id + exact current_section, not guessed array positions. Unknown IDs, mismatched sections and missing evidence are quarantined under rejected_findings. row_index is derived by Python only after validation. Invalid findings never produce auto-edits or engineering approval.
- reviewed_report_sha256 identifies the exact eight-field report snapshot with row IDs. Editing or reordering invalidates the previous review; use review_matches_report before displaying a finding on a later snapshot.
- Only the final analysis is sent to the reviewer; pre-repair drafts are audit-only. Human report text translates technical warnings without modifying the original verification_notes.
- A reference PASS means ID/section/existence compliance only. It is not a test of every numerical or engineering assertion. Sample resolution and human approval boundaries remain.

Verification: regression tests first fail on the original implementation, then pass after the patch. Actual provider replay is opt-in and bounded to one incident analysis session (plus at most one reference correction) and one review. CI artifacts preserve failures before assertions; Vercel deployment remains separately verifiable.
