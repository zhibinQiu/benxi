import { computed } from "vue";
import { useAppPreferences } from "./useAppPreferences";
import { messages } from "../locales";

function resolvePath(dict, key) {
  let cur = dict;
  for (const part of key.split(".")) {
    if (cur == null || typeof cur !== "object") return undefined;
    cur = cur[part];
  }
  return cur;
}

export function useI18n() {
  const { locale } = useAppPreferences();

  const localeLabel = computed(() =>
    locale.value === "zh" ? messages.en.userMenu.switchToEnglish : messages.zh.userMenu.switchToChinese
  );

  function t(key, params) {
    const raw = resolvePath(messages[locale.value], key);
    if (typeof raw !== "string") return key;
    if (!params) return raw;
    return raw.replace(/\{\{(\w+)\}\}/g, (_, name) =>
      params[name] != null ? String(params[name]) : ""
    );
  }

  function routeTitle(routeName, fallback = "") {
    if (!routeName) return fallback;
    const key = `routes.${routeName}`;
    const raw = resolvePath(messages[locale.value], key);
    return typeof raw === "string" ? raw : fallback;
  }

  function scopeLabel(scope) {
    const key = `scope.${scope}`;
    const raw = resolvePath(messages[locale.value], key);
    return typeof raw === "string" ? raw : scope;
  }

  return { locale, localeLabel, t, routeTitle, scopeLabel };
}
