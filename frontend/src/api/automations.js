import { api } from "./http.js";

export function fetchAutomationOverview() {
  return api("/api/v1/automations/overview");
}

export function createAutomation(body) {
  return api("/api/v1/automations", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateAutomation(id, body) {
  return api(`/api/v1/automations/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteAutomation(id) {
  return api(`/api/v1/automations/${id}`, { method: "DELETE" });
}

export function runAutomationNow(id) {
  return api(`/api/v1/automations/${id}/run`, { method: "POST" });
}
