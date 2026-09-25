export const WORKSPACE_SESSION_VERSION = 1;

export function buildWorkspaceSession({
  mode = 'blind',
  eventFile = null,
  rawFile = null,
  eventData = null,
  rawData = null,
  result = null,
  reportRows = [],
  reportVersion = null,
  recovery = null,
  activeTab = 'timeline',
} = {}) {
  return {
    schema_version: WORKSPACE_SESSION_VERSION,
    mode,
    eventFile,
    rawFile,
    eventData,
    rawData,
    result,
    reportRows,
    reportVersion,
    recovery,
    activeTab,
  };
}

export function canRestoreWorkspaceSession(value, mode = 'blind') {
  return Boolean(
    value &&
    value.schema_version === WORKSPACE_SESSION_VERSION &&
    value.mode === mode,
  );
}
