import { computed, ref, watch } from "vue";

const STORAGE_THEME = "platform-theme";
const STORAGE_LOCALE = "platform-locale";

function readStoredTheme() {
  const v = localStorage.getItem(STORAGE_THEME);
  if (v === "light" || v === "dark") return v;
  if (window.matchMedia?.("(prefers-color-scheme: dark)").matches) return "dark";
  return "light";
}

function readStoredLocale() {
  const v = localStorage.getItem(STORAGE_LOCALE);
  return v === "en" ? "en" : "zh";
}

const theme = ref(readStoredTheme());
const locale = ref(readStoredLocale());

function applyThemeToDocument(value) {
  document.documentElement.setAttribute("data-theme", value);
}

function applyLocaleToDocument(value) {
  document.documentElement.lang = value === "en" ? "en" : "zh-CN";
}

watch(
  theme,
  (value) => {
    localStorage.setItem(STORAGE_THEME, value);
    applyThemeToDocument(value);
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
  }

  function toggleLocale() {
    locale.value = locale.value === "zh" ? "en" : "zh";
  }

  function setTheme(value) {
    if (value === "light" || value === "dark") theme.value = value;
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
