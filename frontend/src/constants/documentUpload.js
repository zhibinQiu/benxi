/** 文档中心上传限制（默认与后端 document_upload_max_file_mb 一致，可由 library API 覆盖） */
export const DOCUMENT_UPLOAD_MAX_FILES = 10;
export const DOCUMENT_UPLOAD_MAX_MB_DEFAULT = 200;

let uploadMaxMb = DOCUMENT_UPLOAD_MAX_MB_DEFAULT;

export function setDocumentUploadMaxMb(mb) {
  const n = Number(mb);
  if (Number.isFinite(n) && n > 0) {
    uploadMaxMb = Math.floor(n);
  }
}

export function getDocumentUploadMaxMb() {
  return uploadMaxMb;
}

export function getDocumentUploadMaxBytes() {
  return uploadMaxMb * 1024 * 1024;
}

export function applyUploadLimitsFromLibrary(lib) {
  if (lib?.upload_max_file_mb) {
    setDocumentUploadMaxMb(lib.upload_max_file_mb);
  }
}

export const DOCUMENT_FORMAT_LABELS = Object.freeze({
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
});

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

/** 文档中心允许上传的扩展名（文件选择器 accept） */
export const DOCUMENT_UPLOAD_ACCEPT =
  ".pdf,.doc,.docx,.xls,.xlsx,.csv,.ppt,.pptx,.txt,.md,.markdown";

const UPLOAD_ALLOWED_LABELS = new Set(["pdf", "word", "excel", "csv", "txt", "md", "ppt"]);

export const DOCUMENT_UPLOAD_FORMAT_HINT = "PDF、Word、Excel、CSV、PPT、TXT、MD";

const UPLOAD_EXT_TO_LABEL = Object.freeze({
  pdf: "pdf",
  doc: "word",
  docx: "word",
  dot: "word",
  dotx: "word",
  txt: "txt",
  md: "md",
  markdown: "md",
  rtf: "rtf",
  xls: "excel",
  xlsx: "excel",
  csv: "csv",
  ppt: "ppt",
  pptx: "ppt",
  html: "html",
  htm: "html",
  png: "image",
  jpg: "image",
  jpeg: "image",
  gif: "image",
  webp: "image",
});

const UPLOAD_MIME_TO_LABEL = Object.freeze({
  "application/pdf": "pdf",
  "application/msword": "word",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "word",
  "text/plain": "txt",
  "text/markdown": "md",
  "application/vnd.ms-excel": "excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "excel",
  "text/csv": "csv",
  "application/vnd.ms-powerpoint": "ppt",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation": "ppt",
});

/** 从文件名 / MIME 推断格式标签（与后端 document_format 对齐） */
export function fileFormatLabel(fileName, mimeType = "") {
  const name = String(fileName || "");
  if (name.includes(".")) {
    const ext = name.split(".").pop().toLowerCase().trim();
    if (UPLOAD_EXT_TO_LABEL[ext]) return UPLOAD_EXT_TO_LABEL[ext];
  }
  const mt = String(mimeType || "")
    .split(";")[0]
    .trim()
    .toLowerCase();
  if (UPLOAD_MIME_TO_LABEL[mt]) return UPLOAD_MIME_TO_LABEL[mt];
  if (mt.startsWith("image/")) return "image";
  if (name.includes(".")) {
    const ext = name.split(".").pop().toLowerCase().trim();
    if (ext && /^[a-z0-9]{1,8}$/i.test(ext)) return ext;
  }
  return null;
}

/** 是否为文档中心允许的上传格式 */
export function isAllowedUploadFile(fileName, mimeType = "") {
  const label = fileFormatLabel(fileName, mimeType);
  return Boolean(label && UPLOAD_ALLOWED_LABELS.has(label));
}

export function validateUploadFiles(
  fileList,
  { maxFiles = DOCUMENT_UPLOAD_MAX_FILES, maxBytes, maxMb } = {},
) {
  const limitBytes = maxBytes ?? getDocumentUploadMaxBytes();
  const limitMb = maxMb ?? getDocumentUploadMaxMb();
  const files = fileList.filter(Boolean);
  if (!files.length) return { ok: false, message: "请选择要上传的文件" };
  if (files.length > maxFiles) {
    return { ok: false, message: `最多一次上传 ${maxFiles} 个文件` };
  }
  for (const file of files) {
    if (!isAllowedUploadFile(file.name, file.type)) {
      return {
        ok: false,
        message: `「${file.name}」格式不支持，仅支持 ${DOCUMENT_UPLOAD_FORMAT_HINT}`,
      };
    }
    if (file.size > limitBytes) {
      return {
        ok: false,
        message: `「${file.name}」超过 ${limitMb}MB 限制`,
      };
    }
  }
  return { ok: true, files };
}

/** 新版本须与已有已上传版本格式一致 */
export function validateVersionFormatMatch(versions, file) {
  const uploaded = (versions || []).filter((v) => v.uploaded);
  if (!uploaded.length || !file) return { ok: true };
  const baseline = uploaded.find((v) => v.is_current) || uploaded[0];
  const expected = fileFormatLabel(baseline.file_name, baseline.mime_type);
  const incoming = fileFormatLabel(file.name, file.type);
  if (expected && incoming && expected !== incoming) {
    return {
      ok: false,
      message: `新版本须与已有版本格式一致（当前 ${formatDocumentFormatLabel(expected)}，上传 ${formatDocumentFormatLabel(incoming)}）`,
    };
  }
  return { ok: true };
}
