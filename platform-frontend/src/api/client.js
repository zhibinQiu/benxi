/**
 * 平台 API 聚合入口（兼容既有 `from "../api/client"`）。
 * 新代码请按域引用各模块，例如 `api/http.js`、`api/documents.js`。
 */
export * from "./http.js";
export * from "./auth.js";
export * from "./documents.js";
export * from "./rag.js";
export * from "./dataAnalysis.js";
export * from "./jobs.js";
export * from "./notifications.js";
export * from "./departments.js";
export * from "./monitor.js";
export * from "./todos.js";
export * from "./modelSettings.js";
export * from "./menuSettings.js";
export * from "./compare.js";
export * from "./system.js";
export * from "./translate.js";
export * from "./carbonAssets.js";
export * from "./wechatMp.js";
export * from "./feedSubscriptions.js";
export * from "./subscriptions.js";
export * from "./speech.js";
export * from "./ocr.js";
export * from "./chat.js";

export { formatApiDetail, getApiBase, getToken } from "./http.js";
