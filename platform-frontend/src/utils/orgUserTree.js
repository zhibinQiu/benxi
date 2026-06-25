/**
 * 组织树：无上级（parent_id 为空）的部门为根，其下为子部门与员工。
 * 节点 key：dept:{uuid} | user:{uuid} | dept:{uuid}:members（成员分组，不可勾选）
 */

export const UNASSIGNED_KEY = "dept:__unassigned__";
export const USER_KEY_PREFIX = "user:";
export const MEMBERS_KEY_SUFFIX = ":members";
export const MEMBERS_GROUP_LABEL = "部门成员";

export function userTreeKey(userId) {
  return `${USER_KEY_PREFIX}${userId}`;
}

export function parseUserTreeKey(key) {
  const s = String(key);
  if (!s.startsWith(USER_KEY_PREFIX)) return null;
  const id = s.slice(USER_KEY_PREFIX.length);
  return id || null;
}

export function isUserTreeKey(key) {
  return String(key).startsWith(USER_KEY_PREFIX);
}

export function isDeptTreeKey(key) {
  const s = String(key);
  return s.startsWith("dept:") && s !== UNASSIGNED_KEY && !isMembersGroupKey(s);
}

export function isMembersGroupKey(key) {
  const s = String(key);
  return s.startsWith("dept:") && s.endsWith(MEMBERS_KEY_SUFFIX);
}

export function membersGroupKey(deptId) {
  return `dept:${deptId}${MEMBERS_KEY_SUFFIX}`;
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

/** 直属某部门的员工 id（不含下级部门）。 */
export function userIdsDirectInDept(deptId, users = []) {
  const did = String(deptId);
  return (users || [])
    .filter((u) => userPrimaryDeptId(u) === did)
    .map((u) => String(u.id));
}

function unassignedUserIds(users = []) {
  return (users || []).filter((u) => !userPrimaryDeptId(u)).map((u) => String(u.id));
}

function attachUsersToDeptNodes(deptById, users = [], { memberSelectable = true } = {}) {
  const placed = new Set();
  const membersByDept = new Map();

  for (const u of users || []) {
    const uid = String(u.id);
    const did = userPrimaryDeptId(u);
    if (!did) continue;
    const deptNode = deptById.get(did);
    if (!deptNode) continue;
    if (!membersByDept.has(did)) membersByDept.set(did, []);
    membersByDept.get(did).push({
      key: userTreeKey(uid),
      label: userLabel(u),
      isLeaf: true,
      checkboxDisabled: !memberSelectable,
      disabled: !memberSelectable,
    });
    placed.add(uid);
  }

  for (const [did, memberLeaves] of membersByDept) {
    const deptNode = deptById.get(did);
    if (!deptNode || !memberLeaves.length) continue;
    memberLeaves.sort((a, b) => a.label.localeCompare(b.label, "zh"));
    // 成员挂在「部门成员」分组下，与子部门分列，避免被当成下级部门节点
    deptNode.children.push({
      key: membersGroupKey(did),
      label: MEMBERS_GROUP_LABEL,
      checkboxDisabled: true,
      disabled: true,
      children: memberLeaves,
    });
  }

  return placed;
}

/**
 * @param {object} params
 * @param {Array<{id:string,name:string,parent_id?:string|null}>} params.departments
 * @param {Array<object>} params.users
 * @param {boolean} [params.deptOnly=false] 为 true 时成员仅展示、不可勾选（部门归属选择）
 */
export function buildOrgUserTree({ departments = [], users = [], deptOnly = false }) {
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

  const placed = attachUsersToDeptNodes(deptById, users, {
    memberSelectable: !deptOnly,
  });

  const unassigned = users.filter((u) => !placed.has(String(u.id)));
  if (unassigned.length) {
    roots.push({
      key: UNASSIGNED_KEY,
      label: "未分配部门",
      children: unassigned.map((u) => ({
        key: userTreeKey(u.id),
        label: userLabel(u),
        isLeaf: true,
      })),
    });
  }

  return roots;
}

/** 用户管理等部门选择：展示组织成员，但仅部门节点可勾选。 */
export function buildOrgDeptAssignTree({ departments = [], users = [] }) {
  return buildOrgUserTree({ departments, users, deptOnly: true });
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
  const keys = [...userSet].map((id) => userTreeKey(id));

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

  if (isMembersGroupKey(key)) {
    const deptId = key.slice(5, -MEMBERS_KEY_SUFFIX.length);
    const targets = userIdsDirectInDept(deptId, users);
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

  const uid = parseUserTreeKey(key);
  if (uid) {
    if (action === "check") next.add(uid);
    else next.delete(uid);
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
    const uid = parseUserTreeKey(k);
    if (uid) {
      ids.delete(uid);
      return;
    }
    if (k === UNASSIGNED_KEY) {
      unassignedUserIds(users).forEach((id) => ids.delete(id));
      return;
    }
    if (isMembersGroupKey(k)) {
      const deptId = k.slice(5, -MEMBERS_KEY_SUFFIX.length);
      userIdsDirectInDept(deptId, users).forEach((id) => ids.delete(id));
      return;
    }
    if (isDeptTreeKey(k)) {
      userIdsInDeptSubtree(k.slice(5), users, departments).forEach((id) => ids.delete(id));
    }
  }

  function addKey(k) {
    const uid = parseUserTreeKey(k);
    if (uid) {
      ids.add(uid);
      return;
    }
    if (k === UNASSIGNED_KEY) {
      unassignedUserIds(users).forEach((id) => ids.add(id));
      return;
    }
    if (isMembersGroupKey(k)) {
      const deptId = k.slice(5, -MEMBERS_KEY_SUFFIX.length);
      userIdsDirectInDept(deptId, users).forEach((id) => ids.add(id));
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
