/** 文档版本预览内容加载（Word / 文本编码等） */

import { fetchCompareDocumentContent } from "../api/compare.js";
import { PREVIEW_KIND, resolveDocumentPreviewKind } from "./documentPreview.js";

function looksLikeUtf8(bytes) {
  try {
    new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    return true;
  } catch {
    return false;
  }
}

/** 读取文本 blob，优先 UTF-8，失败时尝试 GB18030（常见 Windows TXT） */
export async function readTextBlob(blob) {
  const buffer = await blob.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  if (looksLikeUtf8(bytes)) {
    return new TextDecoder("utf-8").decode(bytes);
  }
  try {
    return new TextDecoder("gb18030").decode(bytes);
  } catch {
    return new TextDecoder("utf-8").decode(bytes);
  }
}

async function blobHeadBytes(blob, length = 8) {
  return new Uint8Array(await blob.slice(0, length).arrayBuffer());
}

export function blobLooksLikePdf(bytes) {
  return (
    bytes.length >= 4 &&
    bytes[0] === 0x25 &&
    bytes[1] === 0x50 &&
    bytes[2] === 0x44 &&
    bytes[3] === 0x46
  );
}

function blobLooksLikeHtml(text) {
  const head = String(text || "")
    .trimStart()
    .slice(0, 256)
    .toLowerCase();
  return head.startsWith("<!doctype html") || head.startsWith("<html") || head.startsWith("<body");
}

/**
 * 按文件名推断预览类型，并结合 blob 魔数修正（如 .pdf 扩展名但实际为 Markdown）。
 * @returns {Promise<{ kind: string, text?: string, error?: string }>}
 */
export async function resolvePreviewContent(blob, fileName, mimeType = "") {
  if (!blob || blob.size === 0) {
    return { kind: PREVIEW_KIND.UNSUPPORTED, error: "文件内容为空" };
  }

  let kind = resolveDocumentPreviewKind(fileName, mimeType);
  const head = await blobHeadBytes(blob);

  if (kind === PREVIEW_KIND.PDF && !blobLooksLikePdf(head)) {
    const text = await readTextBlob(blob);
    if (text.trim()) {
      if (blobLooksLikeHtml(text)) {
        return { kind: PREVIEW_KIND.HTML };
      }
      return { kind: PREVIEW_KIND.TEXT, text };
    }
    return { kind: PREVIEW_KIND.UNSUPPORTED, error: "文件不是有效的 PDF" };
  }

  if (kind === PREVIEW_KIND.HTML) {
    const text = await readTextBlob(blob);
    if (!blobLooksLikeHtml(text)) {
      return { kind: PREVIEW_KIND.TEXT, text };
    }
  }

  return { kind };
}

export function isLegacyWordFile(fileName, mimeType = "") {
  const lower = String(fileName || "").toLowerCase();
  const mime = String(mimeType || "").toLowerCase();
  if (mime === "application/msword") return true;
  return /\.(doc|dot)$/.test(lower);
}

/**
 * 将 Word 转为 HTML；失败时尝试后端已解析的全文（纯文本降级）。
 * @returns {{ html: string, text: string, messages: object[] }}
 */
function escapeHtml(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** 将后端提取的 Office 正文（## 标题 + 制表符行）渲染为 HTML。 */
export function officeExtractToHtml(fullText) {
  const text = String(fullText || "").trim();
  if (!text) return "";

  const sections = text.split(/\n(?=## )/);
  const parts = [];

  for (const section of sections) {
    const lines = section.trim().split("\n");
    if (!lines.length) continue;

    let title = "";
    let bodyLines = lines;
    if (lines[0].startsWith("## ")) {
      title = lines[0].slice(3).trim();
      bodyLines = lines.slice(1);
    }

    if (title) {
      parts.push(`<h2>${escapeHtml(title)}</h2>`);
    }

    const rows = bodyLines.map((line) => line.trim()).filter(Boolean);
    if (!rows.length) continue;

    const tabular = rows.every((row) => row.includes("\t"));
    if (tabular) {
      parts.push("<table><tbody>");
      for (const row of rows) {
        parts.push("<tr>");
        for (const cell of row.split("\t")) {
          parts.push(`<td>${escapeHtml(cell)}</td>`);
        }
        parts.push("</tr>");
      }
      parts.push("</tbody></table>");
      continue;
    }

    for (const line of rows) {
      parts.push(`<p>${escapeHtml(line)}</p>`);
    }
  }

  return parts.join("\n");
}

async function loadParsedOfficeText(documentId, versionId) {
  if (!documentId || !versionId) return "";
  try {
    const content = await fetchCompareDocumentContent(documentId, versionId);
    return String(content?.full_text || "").trim();
  } catch {
    return "";
  }
}

export async function loadOfficeStructuredPreview(
  blob,
  { documentId = "", versionId = null, fileName = "", mimeType = "" } = {},
) {
  let fullText = await loadParsedOfficeText(documentId, versionId);

  if (!fullText && blob) {
    const kind = resolveDocumentPreviewKind(fileName, mimeType);
    if (kind === PREVIEW_KIND.TEXT) {
      fullText = (await readTextBlob(blob)).trim();
    }
  }

  if (!fullText) {
    const lower = String(fileName || "").toLowerCase();
    if (/\.(ppt|xls)$/.test(lower)) {
      throw new Error("旧版 .ppt / .xls 格式暂不支持在线预览，请下载后查看或转换为 .pptx / .xlsx");
    }
    throw new Error("未能提取文档内容，请下载后在本地应用中打开");
  }

  const html = officeExtractToHtml(fullText);
  if (html) {
    return { html, text: "" };
  }
  return { html: "", text: fullText };
}

export async function loadWordPreview(
  blob,
  { documentId = "", versionId = null, fileName = "" } = {},
) {
  const arrayBuffer = await blob.arrayBuffer();
  try {
    const mammoth = (await import("mammoth")).default;
    const result = await mammoth.convertToHtml({ arrayBuffer });
    return {
      html: result.value || "",
      text: "",
      messages: result.messages || [],
    };
  } catch (primaryError) {
    const text = await loadParsedOfficeText(documentId, versionId);
    if (text) {
      const html = officeExtractToHtml(text);
      if (html) {
        return { html, text: "", messages: [] };
      }
      return { html: "", text, messages: [] };
    }
    const hint = isLegacyWordFile(fileName)
      ? "旧版 .doc 格式暂不支持在线预览，请下载后查看或转换为 .docx"
      : primaryError?.message || "Word 预览加载失败";
    throw new Error(hint);
  }
}
