/**
 * 豆包 (Doubao/Cuttlefish) — 适配器配置
 *
 * 特点:
 * - 字节跳动旗下的 AI 对话产品
 * - 支持图片上传（识图问答）
 * - 支持文字生图（豆包"帮我画"能力）
 * - 支持联网搜索
 * - React SPA 渲染
 */

const { defaultInput, COMMON_CN_QUOTA_PATTERNS, COMMON_DISMISS_PATTERNS } = require('../../factory/providerFactory');

module.exports = {
  key: 'doubao',
  name: '豆包',
  url: 'https://www.doubao.com/chat/',
  authDomains: ['doubao.com/login', 'login.doubao.com'],
  navPostDelay: 4000, // React SPA

  quotaPatterns: [
    ...COMMON_CN_QUOTA_PATTERNS,
    /免费.*次数.*已.*用完/i,
    /今日.*已.*用.*完/i,
  ],

  dismissPatterns: [
    ...COMMON_DISMISS_PATTERNS,
    /新功能.*介绍/i,
    /首次.*使用/i,
  ],

  editorSelectors: [
    'textarea[class*="input"]',
    'textarea[placeholder*="输入"]',
    'textarea[placeholder*="describe"]',
    '[contenteditable="true"]',
    '[role="textbox"]',
  ],

  sendSelectors: [
    'button[class*="send"]',
    '[class*="submit-btn"]',
    'button[aria-label*="发送"]',
    'button[aria-label*="Send"]',
  ],

  sendFallback: 'Enter',

  stopSelectors: [
    'button[class*="stop"]',
    '[class*="stop-btn"]',
  ],

  responseSelectors: [
    '[class*="message-bubble"]',
    '[class*="assistant-message"]',
    '[class*="answer-content"]',
    '[class*="markdown-body"]',
  ],

  stabilityWindow: 10000,
  minResponseLength: 5,

  postResponseHook: async (_page, text) => {
    return text.trim();
  },

  // ── 图片能力 ──
  supportsImageUpload: true,

  uploadImage: async (page, imagePath) => {
    try {
      // 豆包通常有文件上传按钮
      const uploadBtnSelectors = [
        'button[class*="upload"]',
        '[class*="file-upload"]',
        'input[type="file"]',
        'button:has(svg[class*="image"])',
        'button[aria-label*="图片"]',
      ];
      for (const sel of uploadBtnSelectors) {
        const btn = await page.$(sel);
        if (btn) {
          // 如果是 input file
          const tagName = await btn.evaluate(el => el.tagName.toLowerCase());
          if (tagName === 'input') {
            await btn.setInputFiles(imagePath);
          } else {
            await btn.click();
            const [fileChooser] = await Promise.all([
              page.waitForEvent('filechooser', { timeout: 10000 }).catch(() => null),
            ]);
            if (fileChooser) {
              await fileChooser.setFiles(imagePath);
            }
          }
          await new Promise(r => setTimeout(r, 3000));
          return true;
        }
      }
      return false;
    } catch (e) {
      return false;
    }
  },

  supportsImageGen: true,

  inputImageGenPrompt: async (page, editor, prompt) => {
    // 豆包中需在输入框中输入"帮我画..."等触发生图
    const genPrompt = `帮我画一张图: ${prompt}`;
    await defaultInput(page, editor, genPrompt);
  },

  extractImages: async (page) => {
    // 提取生图结果
    const imageUrls = await page.evaluate(() => {
      const imgs = document.querySelectorAll(
        '[class*="generation-result"] img, [class*="image-result"] img, [class*="message-bubble"] img:not([class*="avatar"])'
      );
      return Array.from(imgs)
        .map(img => img.src)
        .filter(s => s && s.startsWith('http'));
    });
    return imageUrls;
  },
};
