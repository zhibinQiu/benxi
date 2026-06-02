/** 认证与用户管理 API */
import { api } from "./http.js";

export async function login(account, password) {
  return api("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ account, password }),
  });
}

export async function registerUser({ phone, email, displayName, password }) {
  const body = {
    phone,
    email,
    display_name: displayName,
    password,
  };
  return api("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchMe() {
  return api("/api/v1/auth/me");
}

export async function updateMe(body) {
  return api("/api/v1/auth/me", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function fetchUsers() {
  return api("/api/v1/users");
}

export async function createUser(body) {
  return api("/api/v1/users", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateUser(userId, body) {
  return api(`/api/v1/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteUser(userId) {
  return api(`/api/v1/users/${userId}`, { method: "DELETE" });
}

export async function fetchRoles() {
  return api("/api/v1/roles");
}
