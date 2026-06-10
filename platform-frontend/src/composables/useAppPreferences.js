import { computed, ref, watch } from "vue";

const STORAGE_THEME = "platform-theme";
const STORAGE_THEME_EXPLICIT = "platform-theme-explicit";
const STORAGE_LOCALE = "platform-locale";

let serverDefaultTheme = "system";
let systemThemeListenerBound = false;

function resolveThemeFromDefault(defaultTheme) {
  if (defaultTheme === "light" || defaultTheme === "dark") return defaultTheme;
  if (window.matchMedia?.("(prefers-color-scheme: dark)").matches) return "dark";
  return "light";
}

function readInitialTheme() {
  const explicit = localStorage.getItem(STORAGE_THEME_EXPLICIT) === "1";
  const stored = localStorage.getItem(STORAGE_THEME);
  if (explicit && (stored === "light" || stored === "dark")) return stored;
  return resolveThemeFromDefault(serverDefaultTheme);
}

function bindSystemThemeListener() {
  if (systemThemeListenerBound || !window.matchMedia) return;
  systemThemeListenerBound = true;
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (event) => {
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

function applyLocaleToDocument(value) {
  document.documentElement.lang = value === "en" ? "en" : "zh-CN";
}

/** 启动时由 client-config 注入默认主题策略 */
export function initAppFromServerConfig(config) {
  const mode = String(config?.default_theme || "system").trim().toLowerCase();
  if (mode === "light" || mode === "dark" || mode === "system") {
    serverDefaultTheme = mode;
  }
  if (localStorage.getItem(STORAGE_THEME_EXPLICIT) !== "1") {
    theme.value = resolveThemeFromDefault(serverDefaultTheme);
  }
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
    isDark,
    toggleTheme,
    toggleLocale,
    setTheme,
    setLocale,
  };
}
