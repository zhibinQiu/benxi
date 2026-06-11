/** 文档中心上传限制（默认与后端 document_upload_max_file_mb 一致，可由 library API 覆盖） */
export const DOCUMENT_UPLOAD_MAX_FILES = 10;
export const DOCUMENT_UPLOAD_MAX_MB_DEFAULT = 200;

let _uploadMaxMb = DOCUMENT_UPLOAD_MAX_MB_DEFAULT;

/** @deprecated 请使用 getDocumentUploadMaxMb() */
export const DOCUMENT_UPLOAD_MAX_MB = DOCUMENT_UPLOAD_MAX_MB_DEFAULT;

/** @deprecated 请使用 getDocumentUploadMaxBytes() */
export const DOCUMENT_UPLOAD_MAX_BYTES =
  DOCUMENT_UPLOAD_MAX_MB_DEFAULT * 1024 * 1024;

export function setDocumentUploadMaxMb(mb) {
  const n = Number(mb);
  if (Number.isFinite(n) && n > 0) {
    _uploadMaxMb = Math.floor(n);
  }
}

export function getDocumentUploadMaxMb() {
  return _uploadMaxMb;
}

export function getDocumentUploadMaxBytes() {
  return _uploadMaxMb * 1024 * 1024;
}

export function applyUploadLimitsFromLibrary(lib) {
  if (lib?.upload_max_file_mb) {
    setDocumentUploadMaxMb(lib.upload_max_file_mb);
  }
}

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
    if (file.size > limitBytes) {
      return {
        ok: false,
        message: `「${file.name}」超过 ${limitMb}MB 限制`,
      };
    }
  }
  return { ok: true, files };
}

const _EXT_LABELS = {
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
};

const _MIME_LABELS = {
  "application/pdf": "pdf",
  "application/msword": "word",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "word",
  "text/plain": "txt",
  "text/markdown": "md",
};

/** 从文件名 / MIME 推断格式标签（与后端 document_format 对齐） */
export function fileFormatLabel(fileName, mimeType = "") {
  const name = String(fileName || "");
  if (name.includes(".")) {
    const ext = name.split(".").pop().toLowerCase().trim();
    if (_EXT_LABELS[ext]) return _EXT_LABELS[ext];
  }
  const mt = String(mimeType || "")
    .split(";")[0]
    .trim()
    .toLowerCase();
  if (_MIME_LABELS[mt]) return _MIME_LABELS[mt];
  if (mt.startsWith("image/")) return "image";
  if (name.includes(".")) {
    const ext = name.split(".").pop().toLowerCase().trim();
    if (ext && /^[a-z0-9]{1,8}$/i.test(ext)) return ext;
  }
  return null;
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
