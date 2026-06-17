/** 文档版本在线预览类型推断 */

export const PREVIEW_KIND = {
  PDF: "pdf",
  IMAGE: "image",
  HTML: "html",
  TEXT: "text",
  WORD: "word",
  UNSUPPORTED: "unsupported",
};

const WORD_EXT = /\.(docx?|dotx?)$/i;
const WORD_MIMES = new Set([
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);

const TEXT_EXT =
  /\.(txt|md|markdown|json|xml|csv|log|yaml|yml|ini|conf|py|js|ts|jsx|tsx|vue|css|scss|less|sql|sh|bat|properties)$/i;

export function resolveDocumentPreviewKind(fileName, mimeType = "") {
  const lower = String(fileName || "").toLowerCase();
  const mime = String(mimeType || "").toLowerCase();

  if (lower.endsWith(".pdf") || mime === "application/pdf") {
    return PREVIEW_KIND.PDF;
  }
  if (/\.(png|jpe?g|gif|webp|svg|bmp|ico)$/i.test(lower) || mime.startsWith("image/")) {
    return PREVIEW_KIND.IMAGE;
  }
  if (/\.(html?|htm)$/i.test(lower) || mime.includes("html")) {
    return PREVIEW_KIND.HTML;
  }
  if (WORD_EXT.test(lower) || WORD_MIMES.has(mime) || mime.includes("wordprocessingml")) {
    return PREVIEW_KIND.WORD;
  }
  if (
    TEXT_EXT.test(lower) ||
    mime.startsWith("text/") ||
    mime === "application/json" ||
    mime === "application/xml" ||
    mime === "application/javascript"
  ) {
    return PREVIEW_KIND.TEXT;
  }
  return PREVIEW_KIND.UNSUPPORTED;
}

export function previewKindLabel(kind) {
  switch (kind) {
    case PREVIEW_KIND.PDF:
      return "PDF";
    case PREVIEW_KIND.IMAGE:
      return "图片";
    case PREVIEW_KIND.HTML:
      return "HTML";
    case PREVIEW_KIND.TEXT:
      return "文本";
    case PREVIEW_KIND.WORD:
      return "Word";
    default:
      return "文件";
  }
}
