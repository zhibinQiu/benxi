import { computed, ref } from "vue";
import { PLATFORM_APP_NAME } from "../constants/platform";
import { useI18n } from "./useI18n";

export const platformAppTitle = ref(PLATFORM_APP_NAME);

export function applyClientBranding(config) {
  const title = String(config?.app_title || "").trim();
  platformAppTitle.value = title || PLATFORM_APP_NAME;
}

export function usePlatformBranding() {
  return { platformAppTitle };
}

/** 登录页、侧边栏等共用的平台展示名称 */
export function useAppDisplayName() {
  const { platformAppTitle } = usePlatformBranding();
  const { t } = useI18n();
  return computed(
    () => platformAppTitle.value || t("app.name") || PLATFORM_APP_NAME
  );
}
