/** 认证与用户管理 API */
import { api } from "./http.js";

export async function login(account, password, captchaToken) {
  return api("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ account, password, captcha_token: captchaToken || "" }),
    preserveOnNavigate: true,
    timeoutMs: 30_000,
  });
}

export async function registerUser({ phone, email, displayName, password, captchaToken }) {
  const body = {
    phone,
    email,
    display_name: displayName,
    password,
    captcha_token: captchaToken || "",
  };
  return api("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify(body),
    preserveOnNavigate: true,
    timeoutMs: 30_000,
  });
}

export async function logout() {
  try {
    await api("/api/v1/auth/logout", { method: "POST" });
  } catch {
    /* 退出以清本地 Token 为主；后台任务不依赖会话 */
  }
}

export async function trialLogin() {
  return api("/api/v1/auth/trial", {
    method: "POST",
    preserveOnNavigate: true,
    timeoutMs: 30_000,
  });
}

export async function fetchMe() {
  return api("/api/v1/auth/me", { preserveOnNavigate: true });
}

export async function updateMe(body) {
  return api("/api/v1/auth/me", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function fetchUsers({ page = 1, page_size = 15 } = {}) {
  const q = new URLSearchParams({ page, page_size });
  return api(`/api/v1/users?${q}`);
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

export async function captchaGenerate() {
  return api("/api/v1/auth/captcha/generate", {
    method: "POST",
    preserveOnNavigate: true,
  });
}

export async function captchaVerify(captchaId, answer) {
  return api("/api/v1/auth/captcha/verify", {
    method: "POST",
    body: JSON.stringify({ captcha_id: captchaId, answer }),
    preserveOnNavigate: true,
  });
}
