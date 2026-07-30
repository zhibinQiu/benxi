/** 从自定义主色生成平台 CSS 变量与 Naive UI 色板
 *  仅覆盖 accent / 焦点等强调色；背景、壳层、侧栏色由 tokens.css 固定，不随主题色变化。
 */

export const DEFAULT_CUSTOM_PRIMARY = "#005A9E";

const HEX_RE = /^#([0-9a-f]{6})$/i;

export function normalizePrimaryColor(value, fallback = DEFAULT_CUSTOM_PRIMARY) {
  const raw = String(value || "").trim();
  if (!HEX_RE.test(raw)) return fallback.toLowerCase();
  return raw.toLowerCase();
}

function parseHex(hex) {
  const h = hex.replace("#", "");
  return {
    r: parseInt(h.slice(0, 2), 16),
    g: parseInt(h.slice(2, 4), 16),
    b: parseInt(h.slice(4, 6), 16),
  };
}

function clampByte(n) {
  return Math.max(0, Math.min(255, Math.round(n)));
}

function rgbToHex(r, g, b) {
  return `#${[r, g, b].map((v) => clampByte(v).toString(16).padStart(2, "0")).join("")}`;
}

function mixHex(a, b, t) {
  const c1 = parseHex(a);
  const c2 = parseHex(b);
  const w = Math.max(0, Math.min(1, t));
  return rgbToHex(
    c1.r + (c2.r - c1.r) * w,
    c1.g + (c2.g - c1.g) * w,
    c1.b + (c2.b - c1.b) * w
  );
}

function lighten(hex, amount) {
  return mixHex(hex, "#ffffff", amount);
}

function darken(hex, amount) {
  return mixHex(hex, "#000000", amount);
}

function rgba(hex, alpha) {
  const { r, g, b } = parseHex(hex);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/** Naive UI 组件色板 */
export function buildCustomNaivePalette(primaryHex, isDark) {
  const base = normalizePrimaryColor(primaryHex);
  if (isDark) {
    const primary = lighten(base, 0.55);
    const primaryHover = lighten(base, 0.7);
    const primaryPressed = lighten(base, 0.35);
    return {
      primary,
      primaryHover,
      primaryPressed,
      primarySuppl: primaryPressed,
      focusBorder: primary,
      focusShadow: `0 0 0 3px ${rgba(primary, 0.24)}`,
      menuActiveBg: rgba(primary, 0.14),
      menuActiveBgHover: rgba(primary, 0.18),
      dropdownActiveBg: rgba(primary, 0.14),
      tabActive: primaryHover,
      dropdownActiveText: primaryHover,
    };
  }
  const primaryHover = lighten(base, 0.12);
  const primaryPressed = darken(base, 0.18);
  return {
    primary: base,
    primaryHover,
    primaryPressed,
    primarySuppl: primaryPressed,
    focusBorder: base,
    focusShadow: `0 0 0 3px ${rgba(base, 0.22)}`,
    menuActiveBg: rgba(base, 0.1),
    menuActiveBgHover: rgba(base, 0.14),
    dropdownActiveBg: rgba(base, 0.1),
    tabActive: base,
    dropdownActiveText: base,
  };
}

/** 仅写入强调色相关 token；不改写背景 / 壳层 / 侧栏底色 */
export function buildCustomCssTokens(primaryHex, isDark) {
  const base = normalizePrimaryColor(primaryHex);
  const secondary = lighten(base, 0.38);
  const tertiary = lighten(base, 0.58);

  if (isDark) {
    const accent = lighten(base, 0.55);
    const accentHover = lighten(base, 0.7);
    const accentPressed = lighten(base, 0.35);
    const accentSecondary = lighten(base, 0.58);
    return {
      "--platform-glass-outline": rgba(accent, 0.16),
      "--liquid-edge-shadow": rgba(base, 0.14),
      "--liquid-flow-b": rgba(base, 0.2),
      "--liquid-flow-c": rgba(secondary, 0.18),
      "--menu-glass-flow-b": rgba(base, 0.12),
      "--menu-glass-accent-soft": rgba(base, 0.14),
      "--menu-glass-accent-mid": rgba(secondary, 0.1),
      "--menu-glass-accent-glow": rgba(base, 0.12),
      "--platform-accent": accent,
      "--platform-accent-hover": accentHover,
      "--platform-accent-pressed": accentPressed,
      "--platform-accent-secondary": accentSecondary,
      "--platform-accent-secondary-hover": accent,
      "--platform-accent-soft": rgba(accent, 0.16),
      "--platform-accent-soft-2": rgba(base, 0.2),
      "--platform-accent-gradient": `linear-gradient(135deg, ${accent} 0%, ${base} 100%)`,
      "--platform-accent-gradient-hover": `linear-gradient(135deg, ${accentHover} 0%, ${accent} 100%)`,
      "--platform-accent-muted": rgba(accent, 0.14),
      "--platform-accent-muted-strong": rgba(accent, 0.22),
      "--platform-accent-border": rgba(accent, 0.28),
      "--platform-accent-border-soft": rgba(accent, 0.18),
      "--platform-accent-stop-a": tertiary,
      "--platform-accent-stop-b": accent,
      "--platform-accent-stop-c": secondary,
      "--platform-accent-stop-d": base,
      "--platform-accent-stop-e": accentPressed,
      "--platform-loader-gradient-start": lighten(base, 0.72),
      "--platform-loader-gradient-mid": accent,
      "--platform-loader-gradient-end": base,
      "--platform-loader-path": rgba(accent, 0.26),
      "--platform-loader-color": accent,
      "--platform-ui-glass-border": rgba(accent, 0.12),
      "--platform-ui-glass-rim": rgba(accent, 0.2),
      "--platform-focus-ring": `0 0 0 3px ${rgba(base, 0.18)}`,
      "--platform-green": accent,
      "--platform-green-hover": accentHover,
      "--platform-green-deep": accentPressed,
      "--platform-green-soft": accentSecondary,
      "--platform-green-surface": rgba(accent, 0.16),
      "--platform-green-surface-2": rgba(base, 0.2),
      "--platform-link": accentHover,
    };
  }

  const accent = base;
  const accentHover = lighten(base, 0.12);
  const accentPressed = darken(base, 0.18);
  const accentSecondary = secondary;

  return {
    "--platform-glass-outline": rgba(base, 0.18),
    "--liquid-flow-b": rgba(base, 0.16),
    "--liquid-flow-c": rgba(secondary, 0.14),
    "--liquid-edge-shadow": rgba(base, 0.12),
    "--menu-glass-flow-b": rgba(base, 0.1),
    "--menu-glass-accent-soft": rgba(base, 0.12),
    "--menu-glass-accent-mid": rgba(secondary, 0.08),
    "--menu-glass-accent-glow": rgba(base, 0.08),
    "--platform-accent": accent,
    "--platform-accent-hover": accentHover,
    "--platform-accent-pressed": accentPressed,
    "--platform-accent-secondary": accentSecondary,
    "--platform-accent-secondary-hover": lighten(base, 0.22),
    "--platform-accent-soft": rgba(base, 0.14),
    "--platform-accent-soft-2": rgba(secondary, 0.16),
    "--platform-accent-gradient": `linear-gradient(135deg, ${lighten(base, 0.18)} 0%, ${accent} 100%)`,
    "--platform-accent-gradient-hover": `linear-gradient(135deg, ${accentHover} 0%, ${accentPressed} 100%)`,
    "--platform-accent-muted": rgba(base, 0.1),
    "--platform-accent-muted-strong": rgba(base, 0.16),
    "--platform-accent-border": rgba(base, 0.22),
    "--platform-accent-border-soft": rgba(base, 0.14),
    "--platform-accent-stop-a": tertiary,
    "--platform-accent-stop-b": accent,
    "--platform-accent-stop-c": accentSecondary,
    "--platform-accent-stop-d": accentPressed,
    "--platform-accent-stop-e": accentHover,
    "--platform-loader-gradient-start": lighten(base, 0.72),
    "--platform-loader-gradient-mid": accentSecondary,
    "--platform-loader-gradient-end": accent,
    "--platform-loader-path": rgba(base, 0.3),
    "--platform-loader-color": lighten(base, 0.18),
    "--platform-ui-glass-border": rgba(base, 0.12),
    "--platform-ui-glass-rim": rgba(base, 0.18),
    "--platform-focus-ring": `0 0 0 3px ${rgba(base, 0.12)}`,
    "--platform-green": accent,
    "--platform-green-hover": accentHover,
    "--platform-green-deep": accentPressed,
    "--platform-green-soft": accentSecondary,
    "--platform-green-surface": rgba(base, 0.14),
    "--platform-green-surface-2": rgba(secondary, 0.16),
    "--platform-link": "#22507c",
  };
}

const appliedCustomKeys = new Set();

export function clearCustomColorTokens() {
  const root = document.documentElement;
  for (const key of appliedCustomKeys) {
    root.style.removeProperty(key);
  }
  appliedCustomKeys.clear();
}

export function applyCustomColorTokens(primaryHex, isDark) {
  clearCustomColorTokens();
  const tokens = buildCustomCssTokens(primaryHex, isDark);
  const root = document.documentElement;
  for (const [key, value] of Object.entries(tokens)) {
    root.style.setProperty(key, value);
    appliedCustomKeys.add(key);
  }
}
