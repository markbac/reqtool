/**
 * labels.js -- Plain labels for ids shown to people (#375). Statuses, types and link types come from the
 * workflow and type configuration (hierarchy.yaml) where it gives a label; otherwise the id is written in
 * sentence case, so `not_reproducible` reads "Not reproducible" and `in_review` reads "In review".
 */

const WORK_TYPES = new Set(['theme', 'initiative', 'epic', 'feature', 'story', 'task', 'bug', 'spike', 'issue']);

// Link types read differently from each end.
const LINK_LABELS = {
  satisfies: ['Satisfies', 'Satisfied by'],
  implements: ['Implements', 'Implemented by'],
  derived_from: ['Derived from', 'Source of'],
  depends_on: ['Depends on', 'Needed by'],
  depended_by: ['Needed by', 'Depends on'],
  traces_to: ['Traces to', 'Traced from'],
  relates_to: ['Relates to', 'Relates to'],
  conflicts_with: ['Conflicts with', 'Conflicts with'],
  supersedes: ['Supersedes', 'Superseded by'],
};

/** `not_reproducible` -> "Not reproducible". Leaves text that already has capitals or spaces alone. */
export function plain(id) {
  if (id === null || id === undefined) return '';
  const s = String(id);
  if (/[A-Z ]/.test(s)) return s;
  const words = s.replace(/[_-]+/g, ' ').trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function workflowFor(reqType, hierarchy) {
  const wfId = hierarchy?.types?.[reqType]?.workflow;
  return wfId ? hierarchy?.workflows?.[wfId] : null;
}

/** The label for a status, from the item type's workflow when it has one. */
export function status(id, reqType, hierarchy) {
  if (!id) return '';
  const wf = workflowFor(reqType, hierarchy);
  const states = wf?.states || [];
  const found = states.find(s => (typeof s === 'string' ? s : s.id) === id);
  if (found && typeof found !== 'string' && found.label) return found.label;
  // Any workflow that knows the state
  for (const w of Object.values(hierarchy?.workflows || {})) {
    const s = (w.states || []).find(x => typeof x !== 'string' && x.id === id && x.label);
    if (s) return s.label;
  }
  return plain(id);
}

/** The label for an item type ("Defect" for `bug`, "Stakeholder need" for `stakeholder_need`). */
export function type(id, hierarchy) {
  const label = hierarchy?.types?.[id]?.label;
  return label || plain(id);
}

/** The label for a link type, from the source's end (``reverse`` for the target's end). */
export function link(id, reverse = false, hierarchy) {
  const configured = (hierarchy?.default_relationship_types || []).find(r => r.id === id);
  if (LINK_LABELS[id]) return LINK_LABELS[id][reverse ? 1 : 0];
  return configured?.label ? plain(configured.label.toLowerCase()) : plain(id);
}

/** `work` or `requirement`, from the type's `family` in hierarchy.yaml, else the built-in default. */
export function family(reqType, hierarchy) {
  const chosen = hierarchy?.types?.[reqType]?.family;
  if (chosen === 'work' || chosen === 'requirement') return chosen;
  return WORK_TYPES.has(reqType) ? 'work' : 'requirement';
}

export const labelOf = { plain, status, type, link, family };
