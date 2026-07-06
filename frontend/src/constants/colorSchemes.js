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

/** Naive UI 主题覆盖色板（仅蓝色，默认方案） */
export const NAIVE_PALETTES = deepFreeze({
  blue: {
    light: {
      primary: "#0067ff",
      primaryHover: "#0058db",
      primaryPressed: "#004abf",
      primarySuppl: "#004abf",
      focusBorder: "#0067ff",
      focusShadow: "0 0 0 2px rgba(0, 103, 255, 0.35)",
      menuActiveBg: "#ececf1",
      menuActiveBgHover: "#e3e3e8",
      dropdownActiveBg: "rgba(0, 103, 255, 0.1)",
      tabActive: "#0067ff",
      dropdownActiveText: "#0067ff",
    },
    dark: {
      primary: "#4d94ff",
      primaryHover: "#66a3ff",
      primaryPressed: "#3385ff",
      primarySuppl: "#3385ff",
      focusBorder: "#4d94ff",
      focusShadow: "0 0 0 2px rgba(77, 148, 255, 0.35)",
      menuActiveBg: "rgba(255, 255, 255, 0.1)",
      menuActiveBgHover: "rgba(255, 255, 255, 0.14)",
      dropdownActiveBg: "rgba(77, 148, 255, 0.14)",
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
