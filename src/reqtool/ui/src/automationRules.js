// Helpers for the automation panel: turn FastAPI 422 details into per-rule messages.
export function ruleErrors(err) {
  const out = {};
  const detail = err?.detail;
  if (!Array.isArray(detail)) return out;
  for (const d of detail) {
    const loc = d.loc || [];
    const idx = loc[0] === 'body' ? loc[1] : loc[0];
    if (typeof idx !== 'number') continue;
    const field = loc.slice(2).join('.');
    const msg = String(d.msg || '').replace(/^Value error, /, '');
    (out[idx] ||= []).push(field ? `${field}: ${msg}` : msg);
  }
  return out;
}

export function newRule(schema) {
  const action = schema.actions[0];
  return {
    name: `Rule ${Date.now().toString().slice(-4)}`,
    enabled: true,
    event: schema.events[0].id,
    condition: {},
    action: action.id,
    target_field: '',
    target_value: '',
  };
}

// Drop empty optional fields before saving.
export function cleanRule(rule) {
  const out = { ...rule };
  if (!out.target_field) delete out.target_field;
  if (!out.target_value) delete out.target_value;
  return out;
}
