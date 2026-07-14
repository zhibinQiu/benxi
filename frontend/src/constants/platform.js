/**
 * 平台系统标题统一后备默认值。
 * 优先级：资源管理（数据库 frontend_app_title）> .env APP_NAME > 此默认值。
 * 所有显示位置（首页大标题、侧栏品牌名、浏览器标签页等）均通过 useAppDisplayName() 获取。
 */
export const PLATFORM_APP_NAME = "本析";
export const PLATFORM_AI_ASSISTANT_NAME = "小析";
export const PLATFORM_COPYRIGHT_HOLDER = "烟台海颐软件";
export const PLATFORM_VERSION = "4.6.0";
export const PLATFORM_VERSION_LABEL = "v4.6.0";
export const PLATFORM_RELEASE_LABEL = "内测";

export function platformCopyrightText() {
  return `Copyright © 2026 本析 ${PLATFORM_VERSION_LABEL}${PLATFORM_RELEASE_LABEL} ${PLATFORM_COPYRIGHT_HOLDER}保留所有权利。`;
}

/** 系统名：标题中的「AI」使用渐变色，其余为普通字色 */
export function splitPlatformBrandTitle(title) {
  const text = String(title || "").trim();
  if (!text) return { prefix: "", highlight: "", suffix: "" };

  const aiIndex = text.indexOf("AI");
  if (aiIndex >= 0) {
    return {
      prefix: text.slice(0, aiIndex),
      highlight: "AI",
      suffix: text.slice(aiIndex + 2),
    };
  }

  return { prefix: "", highlight: "", suffix: text };
}
