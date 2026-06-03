/** 平台品牌、版权与版本（与后端 app/__init__.py、仓库根目录 VERSION 保持一致） */
export const PLATFORM_APP_NAME = "智碳平台AI系统";
export const PLATFORM_COPYRIGHT_HOLDER = "海颐咨询服务部";
export const PLATFORM_VERSION = "3.8.0";
export const PLATFORM_VERSION_LABEL = "v3.8.0";
export const PLATFORM_RELEASE_LABEL = "内测";

export function platformCopyrightText() {
  return `Copyright © 2026 ${PLATFORM_COPYRIGHT_HOLDER} ${PLATFORM_VERSION_LABEL}${PLATFORM_RELEASE_LABEL} 保留所有权利。`;
}
