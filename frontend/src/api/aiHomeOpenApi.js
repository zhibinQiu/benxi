import { api } from "./http";

export async function fetchAiHomeOpenApiSettings() {
  return api("/api/v1/ai-chat/openai-api-settings");
}

export async function updateAiHomeOpenApiSettings(enabled) {
  return api("/api/v1/ai-chat/openai-api-settings", {
    method: "PUT",
    body: JSON.stringify({ enabled: Boolean(enabled) }),
  });
}
