/** 文档库分级（与后端 scope、组织树深度一致） */
export const SCOPE_LABELS = {
  company: "公司级",
  department: "部门级",
  team: "分部级",
  personal: "个人级",
  shared: "分享",
  all: "所有",
};

export const SCOPE_PERM = {
  company: "doc.company",
  department: "doc.dept",
  team: "doc.team",
  personal: "doc.personal",
};

/** Tab 顺序：个人级 → 分部 → 部门 → 公司（分享通过「个人级」下文件夹进入） */
export const LIBRARY_FOLDER_ORDER = [
  "personal",
  "team",
  "department",
  "company",
];

/** 需选择组织节点的分级（根/二级/三级） */
export const ORG_SCOPES = ["company", "department", "team"];
export const DEPT_SCOPES = ORG_SCOPES;
