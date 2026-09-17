/* Deterministic EVENT -> Tag Master resolver for TripLens web ingestion. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.TripLensEventTagResolver = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function clean(value) { return String(value ?? "").trim(); }
  function lookupKey(event) { return `${clean(event.equipment)}::${clean(event.tag || event.event_tag)}`; }

  function buildEventTagIndex(rows) {
    const byRule = new Map();
    const byLookupKey = new Map();
    const bySourceNode = new Map();
    const byTagId = new Map();
    for (const row of rows || []) {
      const ruleId = clean(row.rule_id);
      const key = clean(row.event_lookup_key) || `${clean(row.equipment)}::${clean(row.event_tag)}`;
      const sourceNode = clean(row.source_node);
      const tagId = clean(row.tag_id || row.canonical_tag);
      if (ruleId) byRule.set(ruleId, row);
      if (key) byLookupKey.set(key, row);
      if (tagId) byTagId.set(tagId, row);
      if (sourceNode) {
        const current = bySourceNode.get(sourceNode) || [];
        current.push(row); bySourceNode.set(sourceNode, current);
      }
    }
    return { byRule, byLookupKey, bySourceNode, byTagId };
  }

  function resolveEventTag(event, index) {
    const canonical = clean(event.canonical_tag || event.tag_id);
    if (canonical && index.byTagId.has(canonical)) {
      return { row: index.byTagId.get(canonical), method: "CANONICAL_TAG_ID" };
    }

    const ruleId = clean(event.rule_id);
    if (ruleId && index.byRule.has(ruleId)) {
      return { row: index.byRule.get(ruleId), method: "EVENT_RULE_ID" };
    }

    const sourceNode = clean(event.source_node || event.model_mapping);
    if (sourceNode) {
      const candidates = index.bySourceNode.get(sourceNode) || [];
      if (candidates.length === 1) return { row: candidates[0], method: "EXACT_SOURCE_NODE" };
      if (candidates.length > 1) {
        const key = lookupKey(event);
        const exact = candidates.find((row) => (clean(row.event_lookup_key) || `${clean(row.equipment)}::${clean(row.event_tag)}`) === key);
        if (exact) return { row: exact, method: "SOURCE_NODE_PLUS_EQUIPMENT_TAG" };
      }
    }

    const key = lookupKey(event);
    if (index.byLookupKey.has(key)) {
      return { row: index.byLookupKey.get(key), method: "EQUIPMENT_TAG_EXACT" };
    }
    return null;
  }

  function describeResolvedEvent(event, index) {
    const resolved = resolveEventTag(event, index);
    if (!resolved) {
      return {
        mapping_status: "UNMAPPED_EVENT_TAG",
        lookup_key: lookupKey(event),
        event_tag: clean(event.tag || event.event_tag),
        equipment: clean(event.equipment),
      };
    }
    const row = resolved.row;
    return {
      mapping_status: resolved.method,
      lookup_key: clean(row.event_lookup_key) || lookupKey(event),
      rule_id: clean(row.rule_id),
      canonical_tag: clean(row.tag_id || row.canonical_tag),
      event_tag: clean(row.event_tag || event.tag),
      equipment: clean(row.equipment || event.equipment),
      description: clean(row.description_ko || row.active_message),
      unit: clean(row.unit),
      source_node: clean(row.source_node),
      mapping_method: clean(row.mapping_method),
    };
  }

  return { buildEventTagIndex, resolveEventTag, describeResolvedEvent };
});
