/** 各子系统功能说明（与路由 name 对应，供统一顶栏展示） */
export const FEATURE_DESCRIPTIONS = {
  "ai-home":
    "面向企业碳管理、碳核算与减排路径的专业 AI 助手，支持多轮问答与政策、标准解读。",
  "ai-tools": "聚合常用在线 AI 工具外链，快速跳转至翻译、绘图、办公等能力。",
  translate:
    "智能排版保留 PDF 版式，支持双语对照与术语表；翻译任务可在后台持续进行。",
  rag: "基于企业知识库进行检索增强问答，支持引用溯源与文档定位。",
  "smart-data-query":
    "用自然语言查询业务数据，自动生成统计图表与分析洞察，支持多轮追问。",
  "carbon-qa":
    "面向双碳政策、碳市场与减排实践的智能问答，支持引用来源与图表展示。",
  "smart-forecast": "基于历史数据进行趋势预测与情景分析（内嵌预测子系统）。",
  speech: "会议录音转写、说话人区分、时间线总结与会议记录管理。",
  ocr: "上传图片或 PDF 进行文字识别，支持批量处理（接入后端后可用）。",
  compare: "左右文档对照与语义检索，支持字段匹配与段落级差异分析。",
  "assist-writing":
    "Markdown 双栏编辑，预设提示词由 AI 润色、扩写与续写；发送快捷键 Ctrl/Cmd + Enter。",
  "knowledge-graph": "在知识服务系统中查看与管理知识库、文档切片及知识图谱。",
  documents: "按公司、部门、个人分级管理文档，支持分享授权与个人回收站。",
  "document-detail": "查看文档版本、权限分享与翻译/对比等关联操作。",
  jobs: "查看翻译、对比等后台异步任务的进度与结果。",
  todos: "个人待办清单，支持拖拽排序与 AI 辅助拆解任务。",
  notifications: "平台消息与任务完成通知。",
};

export function getFeatureDescription(routeName) {
  if (!routeName) return "";
  return FEATURE_DESCRIPTIONS[routeName] || "";
}
