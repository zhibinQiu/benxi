import { api } from "./http.js";

export function fetchVisibleMenus() {
  return api("/api/v1/system/menus");
}

export function fetchMenuSettings() {
  return api("/api/v1/admin/menu-settings");
}

export function updateMenuSettings(body) {
  return api("/api/v1/admin/menu-settings", {
    method: "PUT",
    body: JSON.stringify(body),
  });
}
