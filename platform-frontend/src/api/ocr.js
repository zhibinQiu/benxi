/** OCR 识别 REST API */
import { api, getApiBase, getToken } from "./http.js";

export async function fetchOcrMeta() {
  return api("/api/v1/ocr/meta");
}

export async function recognizeOcr({ file, language } = {}) {
  const form = new FormData();
  form.append("file", file);
  if (language) form.append("language", language);
  return api("/api/v1/ocr/recognize", {
    method: "POST",
    body: form,
    timeoutMs: 180000,
  });
}

async function fetchOcrExportResponse({ format, items }) {
  const headers = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${getToken()}`,
  };
  const res = await fetch(`${getApiBase()}/api/v1/ocr/export`, {
    method: "POST",
    headers,
    body: JSON.stringify({ format, items }),
  });
  if (!res.ok) {
    const json = await res.json().catch(() => ({}));
    throw new Error(json?.message || json?.detail || res.statusText || "导出失败");
  }
  return res;
}

export async function downloadOcrExportZip({ format, items }) {
  const res = await fetchOcrExportResponse({ format, items });
  const blob = await res.blob();
  const disp = res.headers.get("Content-Disposition") || "";
  const match = disp.match(/filename="?([^";]+)"?/);
  const suffix = format === "markdown" ? "md" : "json";
  const name = match ? match[1] : `ocr-export-${suffix}.zip`;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}
