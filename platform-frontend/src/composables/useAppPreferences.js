import { computed, ref, watch } from "vue";
import { normalizeColorScheme } from "../constants/colorSchemes.js";
import { prefersDarkColorScheme, subscribeMediaQuery } from "../utils/mediaQuery.js";

const STORAGE_THEME = "platform-theme";
const STORAGE_THEME_EXPLICIT = "platform-theme-explicit";
const STORAGE_LOCALE = "platform-locale";

let serverDefaultTheme = "system";
let systemThemeListenerBound = false;

const colorScheme = ref("purple");

function resolveThemeFromDefault(defaultTheme) {
  if (defaultTheme === "light" || defaultTheme === "dark") return defaultTheme;
  if (prefersDarkColorScheme()) return "dark";
  return "light";
}

function readInitialTheme() {
  const explicit = localStorage.getItem(STORAGE_THEME_EXPLICIT) === "1";
  const stored = localStorage.getItem(STORAGE_THEME);
  if (explicit && (stored === "light" || stored === "dark")) return stored;
  return resolveThemeFromDefault(serverDefaultTheme);
}

function bindSystemThemeListener() {
  if (systemThemeListenerBound) return;
  systemThemeListenerBound = true;
  subscribeMediaQuery("(prefers-color-scheme: dark)", (event) => {
    if (localStorage.getItem(STORAGE_THEME_EXPLICIT) === "1") return;
    if (serverDefaultTheme !== "system") return;
    theme.value = event.matches ? "dark" : "light";
  });
}

function readStoredLocale() {
  const v = localStorage.getItem(STORAGE_LOCALE);
  return v === "en" ? "en" : "zh";
}

const theme = ref(readInitialTheme());
const locale = ref(readStoredLocale());

function applyThemeToDocument(value) {
  document.documentElement.setAttribute("data-theme", value);
}

function applyColorSchemeToDocument(value) {
  const scheme = normalizeColorScheme(value);
  if (scheme === "blue") {
    document.documentElement.setAttribute("data-color-scheme", "blue");
  } else {
    document.documentElement.removeAttribute("data-color-scheme");
  }
}

function applyLocaleToDocument(value) {
  document.documentElement.lang = value === "en" ? "en" : "zh-CN";
}

/** 启动时由 client-config 注入默认主题策略与系统配色 */
export function initAppFromServerConfig(config) {
  const mode = String(config?.default_theme || "system").trim().toLowerCase();
  if (mode === "light" || mode === "dark" || mode === "system") {
    serverDefaultTheme = mode;
  }
  if (localStorage.getItem(STORAGE_THEME_EXPLICIT) !== "1") {
    theme.value = resolveThemeFromDefault(serverDefaultTheme);
  }
  colorScheme.value = normalizeColorScheme(config?.color_scheme);
  applyColorSchemeToDocument(colorScheme.value);
  bindSystemThemeListener();
}

watch(
  theme,
  (value) => {
    applyThemeToDocument(value);
    if (localStorage.getItem(STORAGE_THEME_EXPLICIT) === "1") {
      localStorage.setItem(STORAGE_THEME, value);
    }
  },
  { immediate: true }
);

watch(
  locale,
  (value) => {
    localStorage.setItem(STORAGE_LOCALE, value);
    applyLocaleToDocument(value);
  },
  { immediate: true }
);

export function useAppPreferences() {
  const isDark = computed(() => theme.value === "dark");

  function toggleTheme() {
    theme.value = theme.value === "dark" ? "light" : "dark";
    localStorage.setItem(STORAGE_THEME_EXPLICIT, "1");
    localStorage.setItem(STORAGE_THEME, theme.value);
  }

  function toggleLocale() {
    locale.value = locale.value === "zh" ? "en" : "zh";
  }

  function setTheme(value) {
    if (value === "light" || value === "dark") {
      theme.value = value;
      localStorage.setItem(STORAGE_THEME_EXPLICIT, "1");
      localStorage.setItem(STORAGE_THEME, value);
    }
  }

  function setLocale(value) {
    if (value === "zh" || value === "en") locale.value = value;
  }

  return {
    theme,
    locale,
    colorScheme,
    isDark,
    toggleTheme,
    toggleLocale,
    setTheme,
    setLocale,
  };
}
