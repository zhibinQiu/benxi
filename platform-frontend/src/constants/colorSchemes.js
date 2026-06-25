/** 系统全局配色方案（资源管理 · 前台配置） */

export const COLOR_SCHEME_PURPLE = "purple";
export const COLOR_SCHEME_BLUE = "blue";

export const COLOR_SCHEME_IDS = [COLOR_SCHEME_PURPLE, COLOR_SCHEME_BLUE];

export function normalizeColorScheme(value) {
  const v = String(value || "").trim().toLowerCase();
  return COLOR_SCHEME_IDS.includes(v) ? v : COLOR_SCHEME_PURPLE;
}

/** Naive UI 主题覆盖色板 */
export const NAIVE_PALETTES = {
  purple: {
    light: {
      primary: "#a78bfa",
      primaryHover: "#9374f0",
      primaryPressed: "#7c3aed",
      primarySuppl: "#7c3aed",
      focusBorder: "#a78bfa",
      focusShadow: "0 0 0 3px rgba(167, 139, 250, 0.22)",
      menuActiveBg: "rgba(167, 139, 250, 0.1)",
      menuActiveBgHover: "rgba(167, 139, 250, 0.14)",
      dropdownActiveBg: "rgba(167, 139, 250, 0.1)",
      tabActive: "#a78bfa",
      dropdownActiveText: "#a78bfa",
    },
    dark: {
      primary: "#c4b5fd",
      primaryHover: "#ddd6fe",
      primaryPressed: "#a78bfa",
      primarySuppl: "#a78bfa",
      focusBorder: "#c4b5fd",
      focusShadow: "0 0 0 3px rgba(196, 181, 253, 0.24)",
      menuActiveBg: "rgba(196, 181, 253, 0.14)",
      menuActiveBgHover: "rgba(196, 181, 253, 0.18)",
      dropdownActiveBg: "rgba(196, 181, 253, 0.14)",
      tabActive: "#ddd6fe",
      dropdownActiveText: "#ddd6fe",
    },
  },
  blue: {
    light: {
      primary: "#2D4E9D",
      primaryHover: "#3A60B8",
      primaryPressed: "#243F7E",
      primarySuppl: "#243F7E",
      focusBorder: "#2D4E9D",
      focusShadow: "0 0 0 3px rgba(45, 78, 157, 0.22)",
      menuActiveBg: "rgba(45, 78, 157, 0.1)",
      menuActiveBgHover: "rgba(45, 78, 157, 0.14)",
      dropdownActiveBg: "rgba(45, 78, 157, 0.1)",
      tabActive: "#2D4E9D",
      dropdownActiveText: "#2D4E9D",
    },
    dark: {
      primary: "#9BB5DC",
      primaryHover: "#B8CBE8",
      primaryPressed: "#7BA3D4",
      primarySuppl: "#7BA3D4",
      focusBorder: "#9BB5DC",
      focusShadow: "0 0 0 3px rgba(155, 181, 220, 0.24)",
      menuActiveBg: "rgba(155, 181, 220, 0.14)",
      menuActiveBgHover: "rgba(155, 181, 220, 0.18)",
      dropdownActiveBg: "rgba(155, 181, 220, 0.14)",
      tabActive: "#B8CBE8",
      dropdownActiveText: "#B8CBE8",
    },
  },
};

export function getNaivePalette(colorScheme, isDark) {
  const scheme = normalizeColorScheme(colorScheme);
  const mode = isDark ? "dark" : "light";
  return NAIVE_PALETTES[scheme][mode];
}
