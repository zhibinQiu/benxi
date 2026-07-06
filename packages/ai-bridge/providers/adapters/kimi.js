/**
 * Kimi (月之暗面 Moonshot) — 适配器配置
 *
 * 特点:
 * - React SPA, 每次调用需新建会话
 * - 支持图片上传（识图问答）
 * - 支持联网搜索暂停检测
 * - 自适应稳定性窗口 (5-30s)
 * - send-button-container disabled 检测
 */

const { defaultInput, COMMON_DISMISS_PATTERNS } = require('../../factory/providerFactory');

module.exports = {
  key: 'kimi',
  name: 'Kimi',
  url: 'https://kimi.moonshot.cn/',
  authDomains: ['kimi.moonshot.cn/login', 'moonshot.cn/login'],
  navPostDelay: 4000, // React SPA 渲染时间

  quotaPatterns: [
    /额度.*(?:已|用).*(?:完|尽)/i,
    /次数.*(?:已|用).*(?:完|尽)/i,
    /请.*(?:充值|升级)/i,
  ],

  dismissPatterns: [
    ...COMMON_DISMISS_PATTERNS,
    /版本.*更新/i,
  ],

  // 每次新建会话
  preInputHook: async (page) => {
    // 尝试点击"新建会话"
    const newChatBtns = [
      'a[href*="new"]', '[class*="new-chat"]', '[class*="new-session"]',
      'button:has-text("新建")', '[class*="sidebar-new"]',
    ];
    for (const sel of newChatBtns) {
      try {
        const btn = await page.$(sel);
        if (btn && await btn.isVisible()) {
          await btn.click();
          await new Promise(r => setTimeout(r, 2000));
          return;
        }
      } catch (_) {}
    }
    // 没找到新建按钮，可能是已在空白页
  },

  editorSelectors: [
    '.chat-input-editor',
    '[contenteditable="true"][role="textbox"]',
    '[contenteditable="true"]',
    '[class*="input"] [contenteditable]',
  ],

  // 自定义发送: 检测 disabled 类
  customSend: async (page) => {
    // 查找发送按钮容器
    const sendBtnSelectors = [
      '.send-button-container button',
      '[class*="send-button"]',
      'button[class*="send"]',
    ];
    for (const sel of sendBtnSelectors) {
      try {
        const btn = await page.$(sel);
        if (btn) {
          const isDisabled = await btn.evaluate(el =>
            el.disabled || el.getAttribute('aria-disabled') === 'true' ||
            el.closest('.send-button-container')?.classList.contains('disabled')
          );
          if (!isDisabled) {
            await btn.click();
            return true;
          }
        }
      } catch (_) {}
    }
    // 兜底快捷键
    await page.keyboard.press('Enter');
    return true;
  },

  sendFallback: 'Enter',

  stopSelectors: [
    'button[class*="stop"]',
    '[class*="stop-generation"]',
  ],

  responseSelectors: [
    '[class*="chat-content-item-assistant"]',
    '[class*="segment-content"]',
    '[class*="message-content"]',
  ],

  stabilityWindow: 8000,
  minResponseLength: 10,

  stillGeneratingCheck: async (page) => {
    // 检测搜索暂停
    const searchText = await page.evaluate(() => document.body.innerText || '').catch(() => '');
    return searchText.includes('搜索') && !searchText.includes('搜索完成');
  },

  postResponseHook: async (_page, text) => {
    // 去掉开头可能的"正在思考..."等占位符
    return text.replace(/^正在.*?(?:思考|搜索|理解).*?\n/gm, '').trim();
  },

  // ── 图片能力 ──
  supportsImageUpload: true,

  uploadImage: async (page, imagePath) => {
    // Kimi 支持拖拽/粘贴图片 或通过文件选择器
    try {
      // 方式1: 找到文件输入
      const fileInput = await page.$('input[type="file"], input[accept*="image"]');
      if (fileInput) {
        await fileInput.setInputFiles(imagePath);
        await new Promise(r => setTimeout(r, 3000));
        return true;
      }
      // 方式2: 触发粘贴事件（需要读取文件内容）
      return false;
    } catch (e) {
      return false;
    }
  },

  supportsImageGen: false, // Kimi 暂不原生支持文字生图
};
