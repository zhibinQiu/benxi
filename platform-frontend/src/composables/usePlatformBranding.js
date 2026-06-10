import { ref } from "vue";
import { PLATFORM_APP_NAME } from "../constants/platform";

export const platformAppTitle = ref(PLATFORM_APP_NAME);

export function applyClientBranding(config) {
  const title = String(config?.app_title || "").trim();
  platformAppTitle.value = title || PLATFORM_APP_NAME;
}

export function usePlatformBranding() {
  return { platformAppTitle };
}
