/**
 * DeepSeek — 适配器配置
 *
 * 特点:
 * - 标准管线，textarea 输入框
 * - ds-markdown 响应
 * - 支持图片上传（识图问答，DeepSeek-VL）
 * - 支持阅读链接
 * - 停止按钮 hidden 模式
 */

const { defaultInput, COMMON_CN_QUOTA_PATTERNS, COMMON_DISMISS_PATTERNS } = require('../../factory/providerFactory');

module.exports = {
  key: 'deepseek',
  name: 'DeepSeek',
  url: 'https://chat.deepseek.com/',
  authDomains: ['chat.deepseek.com/login', 'deepseek.com/login'],
  navPostDelay: 3000,

  quotaPatterns: [
    ...COMMON_CN_QUOTA_PATTERNS,
  ],

  dismissPatterns: [
    ...COMMON_DISMISS_PATTERNS,
    /更新.*公告/i,
    /新版本/i,
  ],

  editorSelectors: [
    'textarea[placeholder*="给 DeepSeek 发送消息"]',
    'textarea[placeholder*="DeepSeek"]',
    'textarea[class*="chat-input"]',
    'textarea',
  ],

  sendSelectors: [
    '.ds-button--primary.ds-button--filled.ds-button--circle',
    'button[class*="send"]',
    'button[class*="submit"]',
  ],

  sendFallback: 'Enter',

  stopSelectors: [
    'button[class*="stop"]',
    '[class*="stop-generation"]',
  ],

  responseSelectors: [
    '.ds-markdown',
    '.ds-assistant-message-main-content',
    '[class*="message-content"]',
  ],

  responseSelectorTimeout: 60000,
  stabilityWindow: 12000,
  minResponseLength: 5,

  postResponseHook: async (_page, text) => {
    return text.trim();
  },

  // ── 图片能力 ──
  supportsImageUpload: true,

  uploadImage: async (page, imagePath) => {
    try {
      // DeepSeek 的文件上传按钮
      const uploadBtnSelectors = [
        'input[type="file"]',
        'button[class*="upload"]',
        '[class*="file-upload"]',
        'button:has(svg[class*="paperclip"])',
        'button:has(svg[class*="attachment"])',
        'button[aria-label*="上传"]',
      ];
      for (const sel of uploadBtnSelectors) {
        const btn = await page.$(sel);
        if (btn) {
          const tagName = await btn.evaluate(el => el.tagName.toLowerCase());
          if (tagName === 'input') {
            await btn.setInputFiles(imagePath);
            await new Promise(r => setTimeout(r, 3000));
            return true;
          } else {
            await btn.click();
            const [fileChooser] = await Promise.all([
              page.waitForEvent('filechooser', { timeout: 10000 }).catch(() => null),
            ]);
            if (fileChooser) {
              await fileChooser.setFiles(imagePath);
              await new Promise(r => setTimeout(r, 3000));
              return true;
            }
          }
        }
      }
      return false;
    } catch (e) {
      return false;
    }
  },

  supportsImageGen: false, // DeepSeek 目前不支持文字生图
};
