/**
 * 全局浮层层级（数值越大越靠上）
 *
 * 系统提醒（删除确认、会话失效等）必须高于功能弹窗（后台任务、表单弹窗等）。
 */
export const PLATFORM_Z = {
  /** 下拉菜单、Popover 等跟随层 */
  dropdown: 10000,
  /** 顶栏后台任务 / 通知 / 助手 flyout */
  flyout: 10050,
  /** Tooltip（须高于 flyout 内按钮） */
  tooltip: 10100,
  /** 功能弹窗：表单、文档选择、对比工作台等 n-modal */
  featureModal: 10300,
  /** 功能弹窗内的 Select / Cascader 下拉层（须高于 featureModal 遮罩） */
  selectInModal: 10400,
  /** 系统 Toast */
  message: 10900,
  /** 系统确认框：删除 / 操作确认 / 登录失效（最高交互层） */
  systemDialog: 11000,
};
