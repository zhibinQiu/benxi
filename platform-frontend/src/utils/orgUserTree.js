/**
 * 组织树：无上级（parent_id 为空）的部门为根，其下为子部门与员工。
 * 节点 key：dept:{uuid} | 员工 uuid
 */

export const UNASSIGNED_KEY = "dept:__unassigned__";

export function isUserTreeKey(key) {
  return !String(key).startsWith("dept:");
}

export function isDeptTreeKey(key) {
  const s = String(key);
  return s.startsWith("dept:") && s !== UNASSIGNED_KEY;
}

/** 用户唯一部门 id（全局每人至多一个部门）。 */
export function userPrimaryDeptId(user) {
  if (!user) return null;
  if (user.department_id != null && user.department_id !== "") {
    return String(user.department_id);
  }
  const ids = (user.department_ids || []).map(String);
  return ids[0] || null;
}

export function userLabel(user) {
  if (!user) return "—";
  const name = (user.display_name || user.username || user.phone || "").trim();
  return name || "—";
}

function sortDeptsByName(departments) {
  return [...(departments || [])].sort((a, b) =>
    (a.name || "").localeCompare(b.name || "", "zh")
  );
}

function deptByIdMap(departments) {
  return new Map((departments || []).map((d) => [String(d.id), d]));
}

function descendantDeptIds(rootDeptId, departments) {
  const ids = new Set([String(rootDeptId)]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const d of departments || []) {
      const did = String(d.id);
      const pid = d.parent_id ? String(d.parent_id) : null;
      if (pid && ids.has(pid) && !ids.has(did)) {
        ids.add(did);
        changed = true;
      }
    }
  }
  return ids;
}

/** 部门及其子部门范围内的员工 id。 */
export function userIdsInDeptSubtree(deptId, users = [], departments = []) {
  const scope = descendantDeptIds(deptId, departments);
  const ids = [];
  for (const u of users || []) {
    const did = userPrimaryDeptId(u);
    if (did && scope.has(did)) ids.push(String(u.id));
  }
  return ids;
}

function unassignedUserIds(users = []) {
  return (users || []).filter((u) => !userPrimaryDeptId(u)).map((u) => String(u.id));
}

/**
 * @param {object} params
 * @param {Array<{id:string,name:string,parent_id?:string|null}>} params.departments
 * @param {Array<object>} params.users
 */
export function buildOrgUserTree({ departments = [], users = [] }) {
  const deptList = sortDeptsByName(departments);
  const deptById = new Map();
  for (const d of deptList) {
    deptById.set(String(d.id), {
      key: `dept:${d.id}`,
      label: d.name || "未命名部门",
      children: [],
    });
  }

  const roots = [];
  for (const d of deptList) {
    const node = deptById.get(String(d.id));
    const pid = d.parent_id ? String(d.parent_id) : null;
    if (pid && deptById.has(pid)) {
      deptById.get(pid).children.push(node);
    } else {
      roots.push(node);
    }
  }

  const placed = new Set();
  for (const u of users) {
    const uid = String(u.id);
    const leaf = { key: uid, label: userLabel(u), isLeaf: true };
    const did = userPrimaryDeptId(u);
    if (!did) continue;
    const deptNode = deptById.get(did);
    if (!deptNode) continue;
    if (!deptNode.children.some((c) => c.key === uid)) {
      deptNode.children.push(leaf);
    }
    placed.add(uid);
  }

  const unassigned = users.filter((u) => !placed.has(String(u.id)));
  if (unassigned.length) {
    roots.push({
      key: UNASSIGNED_KEY,
      label: "未分配部门",
      children: unassigned.map((u) => ({
        key: String(u.id),
        label: userLabel(u),
        isLeaf: true,
      })),
    });
  }

  return roots;
}

export function buildOrgDeptTree({ departments = [] }) {
  const deptList = sortDeptsByName(departments);
  const deptById = new Map();
  for (const d of deptList) {
    deptById.set(String(d.id), {
      key: `dept:${d.id}`,
      label: d.name || "未命名部门",
      children: [],
    });
  }

  const roots = [];
  for (const d of deptList) {
    const node = deptById.get(String(d.id));
    const pid = d.parent_id ? String(d.parent_id) : null;
    if (pid && deptById.has(pid)) {
      deptById.get(pid).children.push(node);
    } else {
      roots.push(node);
    }
  }

  return roots;
}

export function defaultExpandedDeptKeys(departments = []) {
  return (departments || []).map((d) => `dept:${d.id}`);
}

/** 分享选人：由已选用户 id 推导树上应勾选的节点（含“全选”的部门节点）。 */
export function treeCheckedKeysFromUserIds(userIds, users = [], departments = []) {
  const userSet = new Set((userIds || []).map(String));
  const keys = [...userSet];

  for (const d of departments || []) {
    const subtree = userIdsInDeptSubtree(d.id, users, departments);
    if (subtree.length > 0 && subtree.every((id) => userSet.has(id))) {
      keys.push(`dept:${d.id}`);
    }
  }

  const unassigned = unassignedUserIds(users);
  if (unassigned.length > 0 && unassigned.every((id) => userSet.has(id))) {
    keys.push(UNASSIGNED_KEY);
  }

  return keys;
}

/** 分享选人：部门下仅部分用户选中时为半选。 */
export function treeIndeterminateKeysFromUserIds(userIds, users = [], departments = []) {
  const userSet = new Set((userIds || []).map(String));
  const keys = [];

  for (const d of departments || []) {
    const subtree = userIdsInDeptSubtree(d.id, users, departments);
    if (!subtree.length) continue;
    const picked = subtree.filter((id) => userSet.has(id)).length;
    if (picked > 0 && picked < subtree.length) {
      keys.push(`dept:${d.id}`);
    }
  }

  const unassigned = unassignedUserIds(users);
  if (unassigned.length) {
    const picked = unassigned.filter((id) => userSet.has(id)).length;
    if (picked > 0 && picked < unassigned.length) {
      keys.push(UNASSIGNED_KEY);
    }
  }

  return keys;
}

/**
 * 分享树勾选变更：勾选部门 → 该部门及下级所有用户；勾选用户 → 仅该用户。
 * @param {string[]} checkedUserIds 当前已选用户
 * @param {{ node?: { key: string }, action?: 'check'|'uncheck' }} meta
 */
export function applyUserPickerCheckChange(
  checkedUserIds,
  meta,
  users = [],
  departments = []
) {
  const node = meta?.node;
  const action = meta?.action;
  if (!node || !action) {
    return [...new Set((checkedUserIds || []).map(String))];
  }

  const key = String(node.key);
  const next = new Set((checkedUserIds || []).map(String));

  if (key === UNASSIGNED_KEY) {
    const targets = unassignedUserIds(users);
    if (action === "check") targets.forEach((id) => next.add(id));
    else targets.forEach((id) => next.delete(id));
    return [...next];
  }

  if (isDeptTreeKey(key)) {
    const targets = userIdsInDeptSubtree(key.slice(5), users, departments);
    if (action === "check") targets.forEach((id) => next.add(id));
    else targets.forEach((id) => next.delete(id));
    return [...next];
  }

  if (isUserTreeKey(key)) {
    if (action === "check") next.add(key);
    else next.delete(key);
  }

  return [...next];
}

/**
 * 无 meta 时根据树勾选 diff 同步用户列表（勾选部门 → 下级用户；勾选用户 → 仅该用户）。
 */
export function applyUserPickerKeysDiff(
  prevDisplayKeys,
  nextDisplayKeys,
  checkedUserIds,
  users = [],
  departments = []
) {
  const prev = new Set((prevDisplayKeys || []).map(String));
  const next = new Set((nextDisplayKeys || []).map(String));
  const added = [...next].filter((k) => !prev.has(k));
  const removed = [...prev].filter((k) => !next.has(k));
  const ids = new Set((checkedUserIds || []).map(String));

  function removeKey(k) {
    if (isUserTreeKey(k)) {
      ids.delete(k);
      return;
    }
    if (k === UNASSIGNED_KEY) {
      unassignedUserIds(users).forEach((id) => ids.delete(id));
      return;
    }
    if (isDeptTreeKey(k)) {
      userIdsInDeptSubtree(k.slice(5), users, departments).forEach((id) => ids.delete(id));
    }
  }

  function addKey(k) {
    if (isUserTreeKey(k)) {
      ids.add(k);
      return;
    }
    if (k === UNASSIGNED_KEY) {
      unassignedUserIds(users).forEach((id) => ids.add(id));
      return;
    }
    if (isDeptTreeKey(k)) {
      userIdsInDeptSubtree(k.slice(5), users, departments).forEach((id) => ids.add(id));
    }
  }

  removed.forEach(removeKey);
  added.forEach(addKey);
  return [...ids];
}
