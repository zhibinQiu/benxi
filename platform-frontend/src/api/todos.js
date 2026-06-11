/** 待办事项 REST API */
import { api } from "./http.js";

export async function fetchTodos(status) {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  return api(`/api/v1/todos${q}`);
}

export async function createTodo(body) {
  return api("/api/v1/todos", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateTodo(todoId, body) {
  return api(`/api/v1/todos/${todoId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteTodo(todoId) {
  return api(`/api/v1/todos/${todoId}`, { method: "DELETE" });
}

export async function reorderTodos(status, orderedIds) {
  return api("/api/v1/todos/reorder", {
    method: "POST",
    body: JSON.stringify({ status, ordered_ids: orderedIds }),
  });
}

export async function todoLlmPreview(text, mode) {
  return api("/api/v1/todos/llm", {
    method: "POST",
    body: JSON.stringify({ text, mode }),
  });
}

export async function batchCreateTodos(items) {
  return api("/api/v1/todos/batch", {
    method: "POST",
    body: JSON.stringify({ items }),
  });
}

export async function replacePendingTodos(items) {
  return api("/api/v1/todos/pending/replace", {
    method: "PUT",
    body: JSON.stringify({ items }),
  });
}
