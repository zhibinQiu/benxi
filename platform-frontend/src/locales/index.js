import zh from "./zh.js";

/** 当前语言包；英文按需加载 */
export const messages = { zh, en: null };

export const LOCALE_LABELS = {
  zh: "中文",
  en: "English",
};

let enLoader = null;

/** 按需加载语言包，默认 zh 已在首包 */
export async function ensureLocale(locale) {
  if (locale !== "en") return messages.zh;
  if (messages.en) return messages.en;
  if (!enLoader) {
    enLoader = import("./en.js").then((mod) => {
      messages.en = mod.default;
      return messages.en;
    });
  }
  return enLoader;
}
