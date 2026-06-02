/** 文档中心上传限制（与后端 complete_upload 30MB 一致） */
export const DOCUMENT_UPLOAD_MAX_FILES = 10;
export const DOCUMENT_UPLOAD_MAX_BYTES = 30 * 1024 * 1024;
export const DOCUMENT_UPLOAD_MAX_MB = 30;

export const DOCUMENT_FORMAT_LABELS = {
  pdf: "PDF",
  word: "Word",
  txt: "TXT",
  md: "MD",
  excel: "Excel",
  csv: "CSV",
  ppt: "PPT",
  html: "HTML",
  image: "图片",
  zip: "ZIP",
  rar: "RAR",
  archive: "压缩包",
};

export function formatDocumentFormatLabel(code) {
  if (!code) return "—";
  const key = String(code).toLowerCase();
  return DOCUMENT_FORMAT_LABELS[key] || key.toUpperCase();
}

export function titleFromFileName(fileName) {
  const base = String(fileName || "").replace(/^.*[/\\]/, "").trim();
  if (!base) return "";
  const dot = base.lastIndexOf(".");
  return dot > 0 ? base.slice(0, dot) : base;
}

export function validateUploadFiles(fileList, { maxFiles = DOCUMENT_UPLOAD_MAX_FILES } = {}) {
  const files = fileList.filter(Boolean);
  if (!files.length) return { ok: false, message: "请选择要上传的文件" };
  if (files.length > maxFiles) {
    return { ok: false, message: `最多一次上传 ${maxFiles} 个文件` };
  }
  for (const file of files) {
    if (file.size > DOCUMENT_UPLOAD_MAX_BYTES) {
      return {
        ok: false,
        message: `「${file.name}」超过 ${DOCUMENT_UPLOAD_MAX_MB}MB 限制`,
      };
    }
  }
  return { ok: true, files };
}
