/**
 * 主题基准色 — 与 tokens.css / color-schemes.css（Smart Carbon Blue）对齐。
 * Naive themeOverrides 不支持 CSS 变量，故在此集中维护静态值。
 */
export const DARK_THEME = {
  bgBase: "#0A1622",
  bgSecondary: "#071018",
  bgTertiary: "#132536",
  card: "#132536",
  table: "#0A1622",
  text1: "#E8EEF4",
  text2: "#B3C2D1",
  text3: "#7A8FA3",
  border: "rgba(217, 227, 236, 0.12)",
  divider: "rgba(217, 227, 236, 0.08)",
};

export const LIGHT_THEME = {
  bgBase: "#F2F6FA",
  card: "#FFFFFF",
  text1: "#182A3B",
  text2: "#3D556D",
  text3: "#6B7F92",
  border: "#D9E3EC",
  divider: "color-mix(in srgb, #D9E3EC 80%, transparent)",
  menu: "#0D2A47",
  accent: "#F0F7FC",
  primary: "#005A9E",
};
