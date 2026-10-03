// Walk the parentId chain upwards, tolerating cycles in bad data.
export const MAX_CRUMB_DEPTH = 50;

export async function buildBreadcrumb(startParentId, fetchReq, selfUid = null) {
  const crumbs = [];
  const seen = new Set(selfUid ? [selfUid] : []);
  let cur = startParentId;
  while (cur && !seen.has(cur) && crumbs.length < MAX_CRUMB_DEPTH) {
    seen.add(cur);
    try {
      const parent = await fetchReq(cur);
      crumbs.unshift({ uid: parent.uid, id: parent.id, title: parent.title });
      cur = parent.parentId;
    } catch { break; /* parent may not exist */ }
  }
  return crumbs;
}
