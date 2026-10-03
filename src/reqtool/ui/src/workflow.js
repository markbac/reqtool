// Pick the workflow (states + transitions) the server will enforce for an item type.
// The per-type workflow from GET /hierarchy wins; the global /workflow is the fallback,
// exactly as hierarchy_store.validate_transition does on the server.
export function resolveWorkflow(reqType, hierarchy, fallback) {
  const wfId = hierarchy?.types?.[reqType]?.workflow;
  const wf = wfId ? hierarchy?.workflows?.[wfId] : null;
  const chosen = wf?.states?.length ? wf : fallback;
  if (!chosen?.states?.length) return null;
  return { states: chosen.states, transitions: chosen.transitions || {} };
}
