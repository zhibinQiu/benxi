/** 工作笔记 API — 概念：菜单(原文件夹) + 文件(原笔记) */

import { api } from "./http.js";

// ── 菜单（后端路径仍用 folders） ──

export function fetchNoteMenus() {
  return api("/api/v1/notes/folders");
}

/** @deprecated 请用 fetchNoteMenus */
export const fetchNoteFolders = fetchNoteMenus;

export function createNoteMenu(name) {
  return api("/api/v1/notes/folders", {
    method: "POST",
    body: JSON.stringify({ name, parent_id: null }),
  });
}

/** @deprecated 请用 createNoteMenu */
export const createNoteFolder = createNoteMenu;

export function updateNoteMenu(menuId, data) {
  return api(`/api/v1/notes/folders/${menuId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

/** @deprecated 请用 updateNoteMenu */
export const updateNoteFolder = updateNoteMenu;

export function deleteNoteMenu(menuId) {
  return api(`/api/v1/notes/folders/${menuId}`, { method: "DELETE" });
}

/** @deprecated 请用 deleteNoteMenu */
export const deleteNoteFolder = deleteNoteMenu;

// ── 文件（笔记） ──

export function fetchNoteFiles(menuId = null) {
  const params = menuId ? `?folder_id=${menuId}` : "";
  return api(`/api/v1/notes${params}`);
}

/** @deprecated 请用 fetchNoteFiles */
export const fetchNotes = fetchNoteFiles;

export function fetchNoteFile(noteId) {
  return api(`/api/v1/notes/${noteId}`);
}

/** @deprecated 请用 fetchNoteFile */
export const fetchNote = fetchNoteFile;

export function createNoteFile(data) {
  return api("/api/v1/notes", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

/** @deprecated 请用 createNoteFile */
export const createNote = createNoteFile;

export function updateNoteFile(noteId, data) {
  return api(`/api/v1/notes/${noteId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

/** @deprecated 请用 updateNoteFile */
export const updateNote = updateNoteFile;

export function deleteNoteFile(noteId) {
  return api(`/api/v1/notes/${noteId}`, { method: "DELETE" });
}

/** @deprecated 请用 deleteNoteFile */
export const deleteNote = deleteNoteFile;

// ── 批量操作 ──

export function batchDeleteNoteFiles(ids) {
  return api("/api/v1/notes/batch-delete", {
    method: "POST",
    body: JSON.stringify({ ids }),
  });
}

// ── 图片上传 ──

export function uploadNoteImage(file) {
  const formData = new FormData();
  formData.append("file", file);
  return api("/api/v1/notes/images", {
    method: "POST",
    body: formData,
    headers: {},
  });
}

// ── AI 润色 ──

export function polishNoteContent(content, direction = "") {
  return api("/api/v1/notes/polish", {
    method: "POST",
    body: JSON.stringify({ content, direction: direction || "" }),
  });
}

/** 公开分享链接（无需登录即可打开） */
export function getNoteShareUrl(shareToken) {
  if (!shareToken) return "";
  const base = "/ai";
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return `${origin}${base}/api/v1/share/notes/${shareToken}`;
}

/** 生成/覆盖笔记公开分享令牌 */
export function shareNoteFile(noteId, { regenerate = true } = {}) {
  return api(`/api/v1/notes/${noteId}/share`, {
    method: "POST",
    body: JSON.stringify({ regenerate }),
  });
}

/** 撤销笔记公开分享链接 */
export function unshareNoteFile(noteId) {
  return api(`/api/v1/notes/${noteId}/share`, { method: "DELETE" });
}

/** 发布到文档库（后台导入） */
export function publishNoteFile(noteId, { toLibrary = true } = {}) {
  return api(`/api/v1/notes/${noteId}/publish`, {
    method: "POST",
    body: JSON.stringify({
      to_library: !!toLibrary,
      share_link: false,
    }),
  });
}
