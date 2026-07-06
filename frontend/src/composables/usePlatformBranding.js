import { computed, ref } from "vue";
import { PLATFORM_APP_NAME } from "../constants/platform";

/**
 * 后端下发的系统标题（来自 .env 或数据库 frontend_app_title）。
 * 空字符串时使用 PLATFORM_APP_NAME 作为后备。
 */
const platformAppTitle = ref("");

export function applyClientBranding(config) {
  platformAppTitle.value = String(config?.app_title || "").trim();
}

/**
 * 全平台统一的系统展示名称。
 * 优先级：
 *   1. 后端 API 返回的 app_title（资源管理 → 前台配置 → 系统大标题）
 *   2. PLATFORM_APP_NAME 常量（constants/platform.js）
 *
 * 所有显示系统标题的位置（首页大标题、侧栏品牌名、浏览器标签页等）
 * 必须仅通过此 composable 获取，不要直接使用 i18n 或其他来源。
 */
export function useAppDisplayName() {
  return computed(() => {
    const custom = platformAppTitle.value.trim();
    if (custom) {
      return custom;
    }
    return PLATFORM_APP_NAME;
  });
}
