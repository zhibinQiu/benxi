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

/** Naive UI 主题覆盖色板（Smart Carbon Blue） */
export const NAIVE_PALETTES = deepFreeze({
  blue: {
    light: {
      primary: "#005A9E",
      primaryHover: "#00497F",
      primaryPressed: "#003A66",
      primarySuppl: "#003B6B",
      focusBorder: "#7DBCE8",
      focusShadow: "0 0 0 2px rgba(0, 90, 158, 0.18)",
      menuActiveBg: "rgba(255, 255, 255, 0.12)",
      menuActiveBgHover: "rgba(255, 255, 255, 0.16)",
      dropdownActiveBg: "rgba(0, 90, 158, 0.08)",
      tabActive: "#005A9E",
      dropdownActiveText: "#005A9E",
    },
    dark: {
      primary: "#459BDB",
      primaryHover: "#7DBCE8",
      primaryPressed: "#1A7FD4",
      primarySuppl: "#1A7FD4",
      focusBorder: "#7DBCE8",
      focusShadow: "0 0 0 2px rgba(69, 155, 219, 0.22)",
      menuActiveBg: "rgba(255, 255, 255, 0.1)",
      menuActiveBgHover: "rgba(255, 255, 255, 0.14)",
      dropdownActiveBg: "rgba(69, 155, 219, 0.16)",
      tabActive: "#459BDB",
      dropdownActiveText: "#459BDB",
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
