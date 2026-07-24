/** 文档格式 → 图标配色与角标（与 documentUpload.file_format 对齐） */

const FORMAT_ICON_META = Object.freeze({
  pdf: { badge: "PDF", color: "#c62828", soft: "rgba(198, 40, 40, 0.12)" },
  word: { badge: "DOC", color: "#1565c0", soft: "rgba(21, 101, 192, 0.12)" },
  excel: { badge: "XLS", color: "#2e7d32", soft: "rgba(46, 125, 50, 0.12)" },
  csv: { badge: "CSV", color: "#00897b", soft: "rgba(0, 137, 123, 0.12)" },
  ppt: { badge: "PPT", color: "#e65100", soft: "rgba(230, 81, 0, 0.12)" },
  txt: { badge: "TXT", color: "#546e7a", soft: "rgba(84, 110, 122, 0.12)" },
  md: { badge: "MD", color: "#455a64", soft: "rgba(69, 90, 100, 0.12)" },
  html: { badge: "HTML", color: "#ef6c00", soft: "rgba(239, 108, 0, 0.12)" },
  image: { badge: "IMG", color: "#6a1b9a", soft: "rgba(106, 27, 154, 0.12)" },
  zip: { badge: "ZIP", color: "#6d4c41", soft: "rgba(109, 76, 65, 0.12)" },
  rar: { badge: "RAR", color: "#6d4c41", soft: "rgba(109, 76, 65, 0.12)" },
  archive: { badge: "ZIP", color: "#6d4c41", soft: "rgba(109, 76, 65, 0.12)" },
});

const DEFAULT_META = Object.freeze({
  badge: "FILE",
  color: "#78909c",
  soft: "rgba(120, 144, 156, 0.12)",
});

/** @param {string|null|undefined} formatCode */
export function documentFileIconMeta(formatCode) {
  const key = String(formatCode || "")
    .toLowerCase()
    .trim();
  if (key && FORMAT_ICON_META[key]) return FORMAT_ICON_META[key];
  if (key && /^[a-z0-9]{1,6}$/i.test(key)) {
    return {
      badge: key.toUpperCase().slice(0, 4),
      color: DEFAULT_META.color,
      soft: DEFAULT_META.soft,
    };
  }
  return DEFAULT_META;
}
