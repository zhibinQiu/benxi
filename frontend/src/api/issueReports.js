import { api } from "./http.js";

export function fetchIssueReports(status) {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  return api(`/api/v1/issue-reports${qs}`);
}

export function createIssueReport(body) {
  return api("/api/v1/issue-reports", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateIssueReport(id, body) {
  return api(`/api/v1/issue-reports/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteIssueReport(id) {
  return api(`/api/v1/issue-reports/${id}`, { method: "DELETE" });
}
