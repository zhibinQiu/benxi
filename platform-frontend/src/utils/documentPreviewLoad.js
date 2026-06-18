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
    if (documentId && versionId) {
      try {
        const content = await fetchCompareDocumentContent(documentId, versionId);
        const text = String(content?.full_text || "").trim();
        if (text) {
          return { html: "", text, messages: [] };
        }
      } catch {
        /* fallback below */
      }
    }
    const hint = isLegacyWordFile(fileName)
      ? "旧版 .doc 格式暂不支持在线预览，请下载后查看或转换为 .docx"
      : primaryError?.message || "Word 预览加载失败";
    throw new Error(hint);
  }
}
