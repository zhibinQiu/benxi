import { computed, watch } from "vue";
import { useAppPreferences } from "./useAppPreferences";
import { ensureLocale, LOCALE_LABELS, messages } from "../locales";

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

  watch(
    locale,
    (value) => {
      void ensureLocale(value);
    },
    { immediate: true }
  );

  const localeLabel = computed(() => {
    const other = locale.value === "zh" ? "en" : "zh";
    return LOCALE_LABELS[other] || other;
  });

  function activeMessages() {
    return messages[locale.value] || messages.zh;
  }

  function t(key, params) {
    const raw = resolvePath(activeMessages(), key);
    if (typeof raw !== "string") return key;
    if (!params) return raw;
    return raw.replace(/\{\{(\w+)\}\}/g, (_, name) =>
      params[name] != null ? String(params[name]) : ""
    );
  }

  function tm(key) {
    return resolvePath(activeMessages(), key);
  }

  function routeTitle(routeName, fallback = "") {
    if (!routeName) return fallback;
    const key = `routes.${routeName}`;
    const raw = resolvePath(activeMessages(), key);
    return typeof raw === "string" ? raw : fallback;
  }

  function scopeLabel(scope) {
    const key = `scope.${scope}`;
    const raw = resolvePath(activeMessages(), key);
    return typeof raw === "string" ? raw : scope;
  }

  function docStatusLabel(key) {
    if (!key) return "";
    const i18nKey = `documents.status.${key}`;
    const raw = resolvePath(activeMessages(), i18nKey);
    return typeof raw === "string" ? raw : key;
  }

  function docLevelLabel(key) {
    if (!key) return "";
    const i18nKey = `documents.level.${key}`;
    const raw = resolvePath(activeMessages(), i18nKey);
    return typeof raw === "string" ? raw : key;
  }

  function featureLabel(id, field, fallback = "") {
    if (!id || !field) return fallback;
    const key = `features.${id}.${field}`;
    const raw = resolvePath(activeMessages(), key);
    return typeof raw === "string" ? raw : fallback;
  }

  function featureDescription(routeName, fallback = "") {
    if (!routeName) return fallback;
    const key = `featureDescriptions.${routeName}`;
    const raw = resolvePath(activeMessages(), key);
    return typeof raw === "string" ? raw : fallback;
  }

  function chatScopeTitle(scope, fallback = "") {
    if (!scope) return fallback;
    const key = `chatScopes.${scope}.title`;
    const raw = resolvePath(activeMessages(), key);
    return typeof raw === "string" ? raw : fallback;
  }

  const FEATURE_TAG_ALIASES = {
    可用: "available",
    无权限: "noAccess",
    即将推出: "comingSoon",
    待集成: "pendingIntegration",
  };

  function featureTagLabel(tag, fallback = "") {
    const rawTag = String(tag || "").trim();
    if (!rawTag) return fallback;
    const alias = FEATURE_TAG_ALIASES[rawTag];
    if (alias) {
      const localized = t(`systemFunctionsPage.tags.${alias}`);
      if (localized !== `systemFunctionsPage.tags.${alias}`) return localized;
    }
    return rawTag;
  }

  return {
    locale,
    localeLabel,
    t,
    tm,
    routeTitle,
    featureLabel,
    featureDescription,
    chatScopeTitle,
    featureTagLabel,
    scopeLabel,
    docStatusLabel,
    docLevelLabel,
  };
}
