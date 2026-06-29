/** 从自定义主色生成平台 CSS 变量与 Naive UI 色板 */

export const DEFAULT_CUSTOM_PRIMARY = "#0067ff";

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

/** 平台 design token（与 color-schemes.css 蓝色方案结构对齐） */
export function buildCustomCssTokens(primaryHex, isDark) {
  const base = normalizePrimaryColor(primaryHex);
  const secondary = lighten(base, 0.38);
  const tertiary = lighten(base, 0.58);

  if (isDark) {
    const accent = lighten(base, 0.55);
    const accentHover = lighten(base, 0.7);
    const accentPressed = lighten(base, 0.35);
    const accentSecondary = lighten(base, 0.58);
    const bgBase = darken(base, 0.88);
    return {
      "--platform-glass-outline": rgba(accent, 0.16),
      "--platform-glass-border": rgba(accent, 0.16),
      "--platform-glass-depth": `0 8px 24px ${rgba(base, 0.14)}`,
      "--liquid-edge-shadow": rgba(base, 0.14),
      "--liquid-flow-b": rgba(base, 0.2),
      "--liquid-flow-c": rgba(secondary, 0.18),
      "--menu-glass-flow-b": rgba(base, 0.12),
      "--menu-glass-accent-soft": rgba(base, 0.14),
      "--menu-glass-accent-mid": rgba(secondary, 0.1),
      "--menu-glass-accent-glow": rgba(base, 0.12),
      "--platform-bg-base": bgBase,
      "--platform-bg": [
        `radial-gradient(ellipse 90% 70% at 8% 14%, ${rgba(base, 0.22)} 0%, transparent 58%)`,
        `radial-gradient(ellipse 75% 55% at 92% 18%, ${rgba(base, 0.2)} 0%, transparent 55%)`,
        `radial-gradient(ellipse 70% 60% at 74% 88%, ${rgba(secondary, 0.14)} 0%, transparent 52%)`,
        `radial-gradient(ellipse 50% 40% at 38% 48%, ${rgba(base, 0.08)} 0%, transparent 70%)`,
        "var(--platform-bg-base)",
      ].join(", "),
      "--platform-bg-secondary": rgba(darken(base, 0.72), 0.72),
      "--platform-bg-tertiary": rgba(darken(base, 0.62), 0.82),
      "--platform-border": rgba(accent, 0.1),
      "--platform-border-strong": rgba(accent, 0.16),
      "--platform-divider": "rgba(255, 255, 255, 0.06)",
      "--platform-shadow": `0 2px 8px rgba(0, 0, 0, 0.32), 0 12px 32px ${rgba(base, 0.12)}`,
      "--platform-shadow-sm": "0 1px 3px rgba(0, 0, 0, 0.28)",
      "--platform-shadow-lg": "0 16px 56px rgba(0, 0, 0, 0.52)",
      "--platform-accent": accent,
      "--platform-accent-hover": accentHover,
      "--platform-accent-pressed": accentPressed,
      "--platform-accent-secondary": accentSecondary,
      "--platform-accent-secondary-hover": accent,
      "--platform-accent-soft": rgba(accent, 0.16),
      "--platform-accent-soft-2": rgba(base, 0.2),
      "--platform-accent-gradient": `linear-gradient(135deg, ${accent} 0%, ${base} 100%)`,
      "--platform-accent-gradient-hover": `linear-gradient(135deg, ${accentHover} 0%, ${accent} 100%)`,
      "--platform-accent-gradient-soft": `linear-gradient(160deg, ${rgba(darken(base, 0.68), 0.72)} 0%, ${rgba(darken(base, 0.78), 0.68)} 100%)`,
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
      "--platform-shell-gradient": `linear-gradient(135deg, ${rgba(darken(base, 0.82), 0.92)} 0%, ${rgba(darken(base, 0.7), 0.88)} 50%, ${rgba(darken(base, 0.85), 0.92)} 100%)`,
      "--platform-ui-glass-border": rgba(accent, 0.12),
      "--platform-ui-glass-rim": rgba(accent, 0.2),
      "--platform-ui-layer-shadow": [
        "0 1px 0 rgba(255, 255, 255, 0.08) inset",
        "0 10px 28px rgba(0, 0, 0, 0.26)",
        `0 0 0 1px ${rgba(base, 0.06)}`,
      ].join(", "),
      "--platform-focus-ring": `0 0 0 4px ${rgba(accent, 0.28)}`,
      "--platform-modal-shadow": [
        "0 24px 48px rgba(0, 0, 0, 0.36)",
        `0 8px 20px ${rgba(base, 0.1)}`,
      ].join(", "),
    };
  }

  const accent = base;
  const accentHover = lighten(base, 0.12);
  const accentPressed = darken(base, 0.18);
  const accentSecondary = secondary;
  const bgBase = lighten(base, 0.92);

  return {
    "--platform-glass-border": rgba(base, 0.14),
    "--platform-glass-outline": rgba(base, 0.18),
    "--platform-glass-depth": `0 8px 24px ${rgba(base, 0.1)}`,
    "--liquid-flow-b": rgba(base, 0.16),
    "--liquid-flow-c": rgba(secondary, 0.14),
    "--liquid-edge-shadow": rgba(base, 0.12),
    "--menu-glass-flow-b": rgba(base, 0.1),
    "--menu-glass-accent-soft": rgba(base, 0.12),
    "--menu-glass-accent-mid": rgba(secondary, 0.08),
    "--menu-glass-accent-glow": rgba(base, 0.08),
    "--platform-bg-base": bgBase,
    "--platform-bg": [
      `radial-gradient(ellipse 85% 65% at 8% 10%, ${rgba(secondary, 0.24)} 0%, transparent 58%)`,
      `radial-gradient(ellipse 72% 58% at 92% 12%, ${rgba(base, 0.22)} 0%, transparent 55%)`,
      `radial-gradient(ellipse 68% 55% at 78% 90%, ${rgba(base, 0.16)} 0%, transparent 52%)`,
      `radial-gradient(ellipse 58% 48% at 38% 52%, ${rgba(tertiary, 0.14)} 0%, transparent 68%)`,
      "radial-gradient(ellipse 45% 40% at 55% 28%, rgba(255, 255, 255, 0.55) 0%, transparent 70%)",
      "var(--platform-bg-base)",
    ].join(", "),
    "--platform-modal-shadow": [
      `0 24px 48px ${rgba(base, 0.12)}`,
      "0 8px 20px rgba(15, 23, 42, 0.06)",
    ].join(", "),
    "--platform-bg-secondary": rgba(bgBase, 0.82),
    "--platform-bg-tertiary": rgba(lighten(base, 0.86), 0.88),
    "--platform-border": rgba(base, 0.12),
    "--platform-border-strong": rgba(base, 0.2),
    "--platform-divider": rgba(base, 0.1),
    "--platform-shadow": `0 2px 8px ${rgba(base, 0.08)}, 0 8px 24px ${rgba(base, 0.08)}`,
    "--platform-shadow-sm": `0 1px 3px ${rgba(base, 0.06)}`,
    "--platform-shadow-lg": `0 12px 48px ${rgba(base, 0.14)}`,
    "--platform-accent": accent,
    "--platform-accent-hover": accentHover,
    "--platform-accent-pressed": accentPressed,
    "--platform-accent-secondary": accentSecondary,
    "--platform-accent-secondary-hover": lighten(base, 0.22),
    "--platform-accent-soft": rgba(base, 0.14),
    "--platform-accent-soft-2": rgba(secondary, 0.16),
    "--platform-accent-gradient": `linear-gradient(135deg, ${lighten(base, 0.18)} 0%, ${accent} 100%)`,
    "--platform-accent-gradient-hover": `linear-gradient(135deg, ${accentHover} 0%, ${accentPressed} 100%)`,
    "--platform-accent-gradient-soft": `linear-gradient(160deg, ${bgBase} 0%, ${lighten(base, 0.86)} 100%)`,
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
    "--platform-shell-gradient": `linear-gradient(135deg, ${rgba(bgBase, 0.88)} 0%, ${rgba(lighten(base, 0.86), 0.86)} 48%, ${rgba(lighten(base, 0.9), 0.88)} 100%)`,
    "--platform-ui-glass-border": rgba(base, 0.12),
    "--platform-ui-glass-rim": rgba(base, 0.18),
    "--platform-ui-layer-shadow": [
      "0 1px 0 rgba(255, 255, 255, 0.75) inset",
      `0 8px 24px ${rgba(base, 0.08)}`,
      `0 2px 6px ${rgba(base, 0.05)}`,
    ].join(", "),
    "--platform-focus-ring": `0 0 0 4px ${rgba(base, 0.26)}`,
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
