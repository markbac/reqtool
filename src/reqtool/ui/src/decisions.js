/**
 * decisions.js -- How decision statuses are shown. A decision that is still needed is Pending (stored as
 * `proposed`); `open` and `in_progress` are statuses of records not yet migrated from the old TBD kind (#371).
 */

export const PENDING_STATUSES = ['proposed', 'open', 'in_progress'];

export const DECISION_TABS = [['proposed', 'Pending'], ['accepted', 'Accepted'], ['rejected', 'Rejected'],
  ['superseded', 'Superseded'], ['', 'All']];

export const isPendingDecision = d => PENDING_STATUSES.includes(d?.status);

export const decisionStatusLabel = s => (PENDING_STATUSES.includes(s) ? 'Pending'
  : s === 'resolved' ? 'Accepted' : s ? s.charAt(0).toUpperCase() + s.slice(1) : '');
