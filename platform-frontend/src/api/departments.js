/** 部门组织 REST API */
import { api } from "./http.js";

export async function fetchDepartments() {
  return api("/api/v1/departments");
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
