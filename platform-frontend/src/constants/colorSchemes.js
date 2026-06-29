/** 系统全局配色方案（资源管理 · 前台配置） */

import { buildCustomNaivePalette, normalizePrimaryColor } from "../utils/customColorTokens.js";

export const COLOR_SCHEME_PURPLE = "purple";
export const COLOR_SCHEME_BLUE = "blue";
export const COLOR_SCHEME_CUSTOM = "custom";

export const COLOR_SCHEME_IDS = [COLOR_SCHEME_PURPLE, COLOR_SCHEME_BLUE, COLOR_SCHEME_CUSTOM];
export const DEFAULT_COLOR_SCHEME = COLOR_SCHEME_BLUE;

export function normalizeColorScheme(value) {
  const v = String(value || "").trim().toLowerCase();
  return COLOR_SCHEME_IDS.includes(v) ? v : DEFAULT_COLOR_SCHEME;
}

/** Naive UI 主题覆盖色板 */
export const NAIVE_PALETTES = {
  purple: {
    light: {
      primary: "#10a37f",
      primaryHover: "#0d8c6c",
      primaryPressed: "#0a7a5e",
      primarySuppl: "#0a7a5e",
      focusBorder: "#10a37f",
      focusShadow: "0 0 0 2px rgba(16, 163, 127, 0.35)",
      menuActiveBg: "#ececf1",
      menuActiveBgHover: "#e3e3e8",
      dropdownActiveBg: "rgba(16, 163, 127, 0.1)",
      tabActive: "#10a37f",
      dropdownActiveText: "#10a37f",
    },
    dark: {
      primary: "#19c37d",
      primaryHover: "#1dd68a",
      primaryPressed: "#10a37f",
      primarySuppl: "#10a37f",
      focusBorder: "#19c37d",
      focusShadow: "0 0 0 2px rgba(25, 195, 125, 0.35)",
      menuActiveBg: "rgba(255, 255, 255, 0.1)",
      menuActiveBgHover: "rgba(255, 255, 255, 0.14)",
      dropdownActiveBg: "rgba(25, 195, 125, 0.14)",
      tabActive: "#19c37d",
      dropdownActiveText: "#19c37d",
    },
  },
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
};

export function getNaivePalette(colorScheme, isDark, customPrimaryColor) {
  const scheme = normalizeColorScheme(colorScheme);
  if (scheme === COLOR_SCHEME_CUSTOM) {
    return buildCustomNaivePalette(normalizePrimaryColor(customPrimaryColor), isDark);
  }
  const mode = isDark ? "dark" : "light";
  return NAIVE_PALETTES[scheme][mode];
}
