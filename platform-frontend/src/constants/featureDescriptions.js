/** 各子系统功能说明（与路由 name 对应，供统一顶栏展示） */
export const FEATURE_DESCRIPTIONS = {
  "ai-home": "企业级 AI 智能体：多轮对话，结合文档检索与本体图谱增强回答。",
  "ai-tools": "常用在线 AI 工具外链入口。",
  translate: "PDF 版式保留翻译，双语对照与术语表；任务后台执行。",
  "knowledge-search": "知识库检索与问答，分级选库、引用溯源。",
  "smart-data-query": "自然语言查数，自动生成图表与分析洞察。",
  "data-analysis":
    "Excel / CSV 分析 Notebook，AI 生成 pandas 代码，图表运行后自动展示。",
  "carbon-qa": "政策与市场领域智能问答，支持引用溯源。",
  "carbon-assets": "碳配额与 CCER 持仓管理，CEA 行情与模拟交易。",
  "wechat-mp": "跟踪公众号推文，导入文档库供知识检索。",
  "wechat-mp-article": "查看推文正文，导入文档库或跳转原文。",
  "feed-subscriptions": "管理 RSS/Atom 订阅源，拉取资讯并导入文档库。",
  "feed-entry": "查看订阅资讯详情，导入文档库或打开原文。",
  "smart-forecast": "历史数据趋势预测与情景分析。",
  speech: "会议录音转写、说话人区分、纪要生成与会议记录存档；配套语音合成支持多音色朗读与音频导出。",
  "text-to-speech": "文本转自然语音，多音色与情感表达。",
  ocr: "图片或 PDF 内容提取，批量导出 Markdown / JSON。",
  "kg-palantir": "查询与编辑实体关系网络；配置本体类型，文档自动抽取，子图探索联动问答。",
  compare: "文档版本或跨文档左右对照，段落差异与自然语言检索。",
  "assist-writing":
    "Markdown 双栏编辑，AI 润色、扩写与续写；Ctrl/Cmd + Enter 发送。",
  "report-generation":
    "大量召回本地知识片段并扩写为长报告；联网检索、多轮补充与格式调整（非简短归纳问答）。",
  "knowledge-subscriptions":
    "粘贴链接收录资讯，按标题/正文搜索；微信文章 Markdown 排版展示。",
  "subscription-item": "查看已收录资讯，导入个人文档库或打开原文。",
  documents: "公司、部门、个人分级文档管理，分享授权与回收站。",
  "document-detail": "文档版本、权限分享与翻译/对比等操作。",
  jobs: "翻译、对比等后台任务进度与结果。",
  todos: "个人待办清单，拖拽排序与 AI 辅助拆解。",
  notifications: "平台消息与任务完成通知。",
};

export function getFeatureDescription(routeName) {
  if (!routeName) return "";
  return FEATURE_DESCRIPTIONS[routeName] || "";
}
