/** 部门组织 REST API */
import { api } from "./http.js";

export async function fetchDepartments() {
  return api("/api/v1/departments");
}

/** 发布到文库的部门树选择器：返回全部部门层级结构（仅需登录，无需管理员权限）。 */
export async function fetchDepartmentTree() {
  return api("/api/v1/departments/tree");
}

export async function createDepartment(body) {
  return api("/api/v1/departments", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateDepartment(deptId, body) {
  return api(`/api/v1/departments/${deptId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteDepartment(deptId) {
  return api(`/api/v1/departments/${deptId}`, { method: "DELETE" });
}
