/** 提示词管理 API */

import { api } from "./http.js";

export function fetchPrompts({ category, search } = {}) {
  const params = new URLSearchParams();
  if (category) params.set("category", category);
  if (search) params.set("search", search);
  const qs = params.toString();
  return api(`/api/v1/prompts${qs ? `?${qs}` : ""}`);
}

export function fetchPrompt(id) {
  return api(`/api/v1/prompts/${id}`);
}

export function createPrompt({ title, content, category }) {
  return api("/api/v1/prompts", {
    method: "POST",
    body: JSON.stringify({ title, content, category: category || "" }),
  });
}

export function updatePrompt(id, { title, content, category }) {
  return api(`/api/v1/prompts/${id}`, {
    method: "PUT",
    body: JSON.stringify({ title, content, category }),
  });
}

export function deletePrompt(id) {
  return api(`/api/v1/prompts/${id}`, { method: "DELETE" });
}

export function fetchPromptCategories() {
  return api("/api/v1/prompts/categories/summary");
}
