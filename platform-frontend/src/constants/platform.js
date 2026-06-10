/** 平台品牌、版权与版本（与后端 app/__init__.py、仓库根目录 VERSION 保持一致） */
export const PLATFORM_APP_NAME = "智碳平台AI系统";
export const PLATFORM_COPYRIGHT_HOLDER = "海颐咨询服务部";
export const PLATFORM_VERSION = "3.9.3";
export const PLATFORM_VERSION_LABEL = "v3.9.3";
export const PLATFORM_RELEASE_LABEL = "内测";

export function platformCopyrightText() {
  return `Copyright © 2026 ${PLATFORM_COPYRIGHT_HOLDER} ${PLATFORM_VERSION_LABEL}${PLATFORM_RELEASE_LABEL} 保留所有权利。`;
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
