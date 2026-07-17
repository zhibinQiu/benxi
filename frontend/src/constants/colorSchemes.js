/** 系统全局配色方案（资源管理 · 前台配置） */

import { buildCustomNaivePalette, normalizePrimaryColor } from "../utils/customColorTokens.js";

export const COLOR_SCHEME_BLUE = "blue";
export const COLOR_SCHEME_CUSTOM = "custom";

export const COLOR_SCHEME_IDS = Object.freeze([COLOR_SCHEME_BLUE, COLOR_SCHEME_CUSTOM]);
export const DEFAULT_COLOR_SCHEME = COLOR_SCHEME_BLUE;

export function normalizeColorScheme(value) {
  const v = String(value || "").trim().toLowerCase();
  return COLOR_SCHEME_IDS.includes(v) ? v : DEFAULT_COLOR_SCHEME;
}

function deepFreeze(obj) {
  const props = Object.getOwnPropertyNames(obj);
  for (const prop of props) {
    const val = obj[prop];
    if (val && typeof val === "object" && !Object.isFrozen(val)) {
      deepFreeze(val);
    }
  }
  return Object.freeze(obj);
}

/** Naive UI 主题覆盖色板（蓝色系） */
export const NAIVE_PALETTES = deepFreeze({
  blue: {
    light: {
      primary: "#0a6bff",
      primaryHover: "#0058e0",
      primaryPressed: "#004ac2",
      primarySuppl: "#004ac2",
      focusBorder: "#a0a0a0",
      focusShadow: "0 0 0 2px rgba(0, 0, 0, 0.12)",
      menuActiveBg: "#e6e6e6",
      menuActiveBgHover: "#d9d9d9",
      dropdownActiveBg: "rgba(0, 0, 0, 0.06)",
      tabActive: "#0a6bff",
      dropdownActiveText: "#0a6bff",
    },
    dark: {
      primary: "#4d94ff",
      primaryHover: "#6ea3ff",
      primaryPressed: "#3b82ff",
      primarySuppl: "#3b82ff",
      focusBorder: "#585868",
      focusShadow: "0 0 0 2px rgba(255, 255, 255, 0.10)",
      menuActiveBg: "rgba(255, 255, 255, 0.08)",
      menuActiveBgHover: "rgba(255, 255, 255, 0.12)",
      dropdownActiveBg: "rgba(255, 255, 255, 0.08)",
      tabActive: "#4d94ff",
      dropdownActiveText: "#4d94ff",
    },
  },
});

export function getNaivePalette(colorScheme, isDark, customPrimaryColor) {
  const scheme = normalizeColorScheme(colorScheme);
  if (scheme === COLOR_SCHEME_CUSTOM) {
    return buildCustomNaivePalette(normalizePrimaryColor(customPrimaryColor), isDark);
  }
  const mode = isDark ? "dark" : "light";
  return NAIVE_PALETTES[scheme][mode];
}
