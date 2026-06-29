import { api } from "./http";

export async function fetchAipKeys() {
  return api("/api/v1/admin/aip/keys");
}

export async function createAipKey(purpose) {
  return api("/api/v1/admin/aip/keys", {
    method: "POST",
    body: JSON.stringify({ purpose }),
  });
}

export async function deleteAipKey(keyId) {
  return api(`/api/v1/admin/aip/keys/${encodeURIComponent(keyId)}`, {
    method: "DELETE",
  });
}
