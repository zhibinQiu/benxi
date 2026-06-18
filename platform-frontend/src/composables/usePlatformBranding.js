import { computed, ref } from "vue";
import { PLATFORM_APP_NAME } from "../constants/platform";
import { messages } from "../locales";
import { useI18n } from "./useI18n";

/** 后端下发的原始标题；空字符串表示使用 i18n 默认 */
export const platformAppTitle = ref("");

const DEFAULT_ZH_TITLES = new Set(
  [PLATFORM_APP_NAME, messages.zh?.app?.name].filter(Boolean)
);

export function isDefaultPlatformTitle(title) {
  const text = String(title || "").trim();
  return !text || DEFAULT_ZH_TITLES.has(text);
}

export function applyClientBranding(config) {
  platformAppTitle.value = String(config?.app_title || "").trim();
}

export function usePlatformBranding() {
  return { platformAppTitle };
}

/** 登录页、侧边栏、document.title 共用的平台展示名称 */
export function useAppDisplayName() {
  const { platformAppTitle } = usePlatformBranding();
  const { t } = useI18n();
  return computed(() => {
    const custom = platformAppTitle.value.trim();
    if (custom && !isDefaultPlatformTitle(custom)) {
      return custom;
    }
    return t("app.name") || PLATFORM_APP_NAME;
  });
}
