/** 功能页 / 管理页分组 accent（优先 CSS 变量，避免硬编码紫/靛色） */

export const FEATURE_CATEGORY_ACCENTS = Object.freeze({
  document: Object.freeze({
    accent: "#2563eb",
    soft: "rgba(37, 99, 235, 0.12)",
  }),
  tools: Object.freeze({
    accent: "var(--platform-accent)",
    soft: "var(--platform-accent-soft)",
  }),
  ai: Object.freeze({
    accent: "var(--platform-accent)",
    soft: "var(--platform-accent-soft)",
  }),
});

export const ADMIN_RESOURCE_GROUP_ACCENTS = Object.freeze({
  platform: Object.freeze({
    accent: "#0067ff",
    soft: "rgba(0, 103, 255, 0.1)",
  }),
  model: Object.freeze({
    accent: "var(--platform-accent-secondary)",
    soft: "var(--platform-accent-soft)",
  }),
  knowledge: Object.freeze({
    accent: "var(--platform-accent)",
    soft: "var(--platform-accent-soft)",
  }),
  default: Object.freeze({
    accent: "#5b9cf5",
    soft: "rgba(91, 156, 245, 0.1)",
  }),
});

export function categoryAccentStyle(categoryId, palette = FEATURE_CATEGORY_ACCENTS) {
  const entry = palette[categoryId] || palette.tools || palette.default;
  return {
    "--cat-accent": entry.accent,
    "--cat-accent-soft": entry.soft,
  };
}

export function adminResourceGroupAccentStyle(groupId) {
  const entry = ADMIN_RESOURCE_GROUP_ACCENTS[groupId] || ADMIN_RESOURCE_GROUP_ACCENTS.default;
  return {
    "--cat-accent": entry.accent,
    "--cat-accent-soft": entry.soft,
  };
}
