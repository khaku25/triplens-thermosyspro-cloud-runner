/* TripLens report export helper.
 *
 * The live dashboard contains fixed-height/scrollable panels. Printing that DOM
 * only captures the visible slice. This helper builds an isolated report DOM
 * from analysis state so every section is expanded before browser PDF output.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.TripLensReportExport = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const PINPOINT_COLUMNS = [
    "run_id", "pinpoint_rank", "causal_stage", "claim", "disposition",
    "source_system", "event_id", "original_time", "aligned_time", "equipment",
    "event_tag", "canonical_tag", "value", "unit", "state", "evidence_role",
    "logic_id", "mapping_status", "counter_evidence", "recovery_status",
    "review_required",
  ];

  const KNOWN_SECTIONS = [
    ["incident_summary", "Incident Summary"],
    ["critical_events", "Critical Events"],
    ["primary_cause", "Primary Cause"],
    ["direct_trigger", "Direct Trigger"],
    ["propagation", "Propagation"],
    ["causal_chain", "Causal Chain"],
    ["key_evidence", "Key Evidence"],
    ["recovery_check", "Recovery Check"],
    ["gemini_analysis", "Gemini Analysis"],
  ];

  function esc(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function csvCell(value) {
    const text = String(value ?? "");
    return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  }

  function asText(value) {
    if (value == null) return "";
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
    if (Array.isArray(value)) return value.map(asText).filter(Boolean).join("\n");
    return Object.entries(value).map(([k, v]) => `${k}: ${asText(v)}`).join("\n");
  }

  function renderValue(value) {
    if (value == null || value === "") return '<div class="empty">No data</div>';
    if (Array.isArray(value)) {
      if (!value.length) return '<div class="empty">No data</div>';
      return `<div class="list">${value.map((item) => `<div class="item">${renderValue(item)}</div>`).join("")}</div>`;
    }
    if (typeof value === "object") {
      return `<table><tbody>${Object.entries(value).map(([key, val]) =>
        `<tr><th>${esc(key)}</th><td>${renderValue(val)}</td></tr>`).join("")}</tbody></table>`;
    }
    return `<div class="text">${esc(value).replace(/\n/g, "<br>")}</div>`;
  }

  function normalizeSections(report) {
    if (Array.isArray(report.sections)) {
      return report.sections.map((section, index) => ({
        id: section.id || `section-${index + 1}`,
        title: section.title || section.id || `Section ${index + 1}`,
        value: section.value ?? section.content ?? section.data ?? "",
      }));
    }
    return KNOWN_SECTIONS
      .filter(([key]) => report[key] !== undefined)
      .map(([key, title]) => ({ id: key, title, value: report[key] }));
  }

  function buildReportHtml(report) {
    const title = report.title || "TripLens Incident Analysis Report";
    const metadata = report.metadata || {};
    const sections = normalizeSections(report);
    const metaRows = Object.entries(metadata).map(([k, v]) =>
      `<tr><th>${esc(k)}</th><td>${esc(asText(v))}</td></tr>`).join("");
    const sectionHtml = sections.map((section) =>
      `<section class="report-section" id="${esc(section.id)}"><h2>${esc(section.title)}</h2>${renderValue(section.value)}</section>`
    ).join("");

    return `<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)}</title>
<style>
@page{size:A4;margin:12mm 11mm 14mm}
*{box-sizing:border-box}html,body{margin:0;padding:0;background:#fff;color:#18202a;font-family:Arial,"Noto Sans KR",sans-serif;font-size:10.5pt;line-height:1.45}
.report{width:100%;max-width:190mm;margin:0 auto;padding:0}.header{border-bottom:2px solid #18364d;padding:0 0 8mm;margin-bottom:6mm}.header h1{font-size:19pt;margin:0 0 2mm}.sub{font-size:9pt;color:#52616e}
h2{font-size:12.5pt;margin:0 0 3mm;color:#18364d}.report-section{margin:0 0 6mm;padding:4mm;border:1px solid #cdd6dd;border-radius:2mm;break-inside:auto;page-break-inside:auto;overflow:visible!important;max-height:none!important;height:auto!important}
table{width:100%;border-collapse:collapse;table-layout:auto;break-inside:auto}thead{display:table-header-group}tr{break-inside:avoid-page;page-break-inside:avoid}th,td{border:1px solid #d8dfe5;padding:2mm;vertical-align:top;overflow-wrap:anywhere}th{width:28%;background:#f3f6f8;text-align:left;font-weight:700}
.list{display:block}.item{padding:2.5mm 0;border-bottom:1px solid #e3e8ec;break-inside:avoid-page}.item:last-child{border-bottom:0}.text{white-space:normal;overflow-wrap:anywhere}.empty{color:#7a8791;font-style:italic}.footer{margin-top:8mm;padding-top:3mm;border-top:1px solid #ccd4da;font-size:8.5pt;color:#687680}
@media print{html,body{width:auto!important;height:auto!important;overflow:visible!important}.screen-only{display:none!important}.report{max-width:none}.report-section,.list,.item,table{overflow:visible!important;max-height:none!important;height:auto!important}}
</style></head><body><main class="report">
<header class="header"><h1>${esc(title)}</h1><div class="sub">EVENT + RAW Dual Log · read-only accident analysis</div></header>
${metaRows ? `<section class="report-section"><h2>Run Metadata</h2><table><tbody>${metaRows}</tbody></table></section>` : ""}
${sectionHtml}
<footer class="footer">Generated from the current TripLens analysis state. PDF export does not rerun or rewrite the analysis.</footer>
</main></body></html>`;
  }

  function printReport(report) {
    if (typeof window === "undefined" || !window.open) throw new Error("printReport requires a browser window");
    const popup = window.open("", "_blank", "noopener,noreferrer");
    if (!popup) throw new Error("Report window was blocked by the browser");
    popup.document.open();
    popup.document.write(buildReportHtml(report));
    popup.document.close();
    const printWhenReady = () => {
      const fonts = popup.document.fonts && popup.document.fonts.ready ? popup.document.fonts.ready : Promise.resolve();
      fonts.finally(() => { popup.focus(); popup.print(); });
    };
    if (popup.document.readyState === "complete") printWhenReady();
    else popup.addEventListener("load", printWhenReady, { once: true });
    return popup;
  }

  function pinpointRows(report) {
    if (Array.isArray(report.pinpoints)) return report.pinpoints;
    const runId = report.run_id || report.metadata?.run_id || "";
    const sections = normalizeSections(report);
    const rows = [];
    let rank = 1;
    for (const section of sections) {
      const values = Array.isArray(section.value) ? section.value : [section.value];
      for (const value of values) {
        if (value == null || value === "") continue;
        const obj = typeof value === "object" && !Array.isArray(value) ? value : { claim: asText(value) };
        const evidence = Array.isArray(obj.evidence) && obj.evidence.length ? obj.evidence : [{}];
        for (const ev of evidence) {
          rows.push({
            run_id: runId,
            pinpoint_rank: rank,
            causal_stage: String(obj.causal_stage || section.id || "").toUpperCase(),
            claim: obj.claim || obj.title || obj.summary || asText(value),
            disposition: obj.disposition || obj.status || "",
            source_system: ev.source_system || ev.source || obj.source_system || "",
            event_id: ev.event_id || "",
            original_time: ev.original_time || ev.original_time_s || "",
            aligned_time: ev.aligned_time || ev.aligned_time_s || "",
            equipment: ev.equipment || obj.equipment || "",
            event_tag: ev.event_tag || ev.tag || "",
            canonical_tag: ev.canonical_tag || "",
            value: ev.value ?? "",
            unit: ev.unit || "",
            state: ev.state || "",
            evidence_role: ev.evidence_role || ev.role || "",
            logic_id: ev.logic_id || obj.logic_id || "",
            mapping_status: ev.mapping_status || "",
            counter_evidence: obj.counter_evidence || "",
            recovery_status: obj.recovery_status || "",
            review_required: obj.review_required ?? (String(obj.disposition || "").toUpperCase() === "REVIEW_REQUIRED"),
          });
        }
        rank += 1;
      }
    }
    return rows;
  }

  function buildPinpointCsv(report) {
    const rows = pinpointRows(report);
    return [
      PINPOINT_COLUMNS.join(","),
      ...rows.map((row) => PINPOINT_COLUMNS.map((column) => csvCell(row[column])).join(",")),
    ].join("\r\n") + "\r\n";
  }

  function downloadText(filename, text, mimeType) {
    if (typeof document === "undefined") throw new Error("downloadText requires a browser document");
    const blob = new Blob([text], { type: mimeType || "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url; link.download = filename; link.style.display = "none";
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  function downloadPinpointCsv(report, filename) {
    downloadText(filename || "PINPOINT.csv", "\ufeff" + buildPinpointCsv(report), "text/csv;charset=utf-8");
  }

  return {
    PINPOINT_COLUMNS,
    normalizeSections,
    buildReportHtml,
    printReport,
    pinpointRows,
    buildPinpointCsv,
    downloadPinpointCsv,
  };
});
