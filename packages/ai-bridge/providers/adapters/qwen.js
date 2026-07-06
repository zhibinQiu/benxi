/**
 * 通义千问 (Qwen/Tongyi) — 适配器配置
 *
 * 特点:
 * - 阿里云旗下大模型，支持对话、生图（通义万相）、识图
 * - React SPA，3s 渲染延迟
 * - 停止按钮 detached 模式（从 DOM 移除）
 * - 回复带模型名前缀，需 strip
 * - 支持上传图片做识图问答
 */

const { defaultInput, COMMON_CN_QUOTA_PATTERNS, COMMON_DISMISS_PATTERNS } = require('../../factory/providerFactory');

module.exports = {
  key: 'qwen',
  name: '通义千问',
  url: 'https://tongyi.aliyun.com/qianwen/',
  authDomains: ['login.aliyun.com', 'signin.aliyun.com', 'aliyun.com/login'],
  navPostDelay: 3000,

  quotaPatterns: [
    ...COMMON_CN_QUOTA_PATTERNS,
  ],

  dismissPatterns: [
    ...COMMON_DISMISS_PATTERNS,
    /提示/i,
    /体验/i,
  ],

  editorSelectors: [
    '[contenteditable="true"][role="textbox"]',
    '[contenteditable="true"]',
    'textarea',
    '[role="textbox"]',
  ],

  sendSelectors: [], // 千问用 Enter 发送最可靠
  sendFallback: 'Enter',

  stopWaitMode: 'detached',
  stopSelectors: [
    '[class*="stop"] button',
    'button[class*="stop"]',
    '[class*="stop-btn"]',
  ],

  responseSelectors: [
    '[class*="message-select-wrapper-answer"]',
    '[class*="chat-answers-card-wrap"]',
    '[class*="message-select-content-inner"]',
    '[class*="answer-content"]',
  ],

  stabilityWindow: 8000,
  minResponseLength: 5,

  postResponseHook: async (_page, text) => {
    // 去掉模型名前缀: "Qwen2.5-Max:" 等
    return text.replace(/^Qwen[\d.]*-(?:Max|Plus|Turbo|Flash|72B)?[：:\s]*/i, '').trim();
  },

  // ── 图片能力 ──
  supportsImageUpload: true,

  uploadImage: async (page, imagePath) => {
    try {
      // 通义千问的图片上传按钮
      const uploadBtnSelectors = [
        'input[type="file"][accept*="image"]',
        'button[class*="image-upload"]',
        '[class*="upload-btn"]',
        'button[aria-label*="图片"]',
        'button:has(svg[class*="image"])',
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

  supportsImageGen: true,

  inputImageGenPrompt: async (page, editor, prompt) => {
    // 千问中使用通义万相生图
    const genPrompt = `使用通义万相画图: ${prompt}`;
    await defaultInput(page, editor, genPrompt);
  },

  extractImages: async (page) => {
    const imageUrls = await page.evaluate(() => {
      const imgs = document.querySelectorAll(
        'img[class*="generated"], img[class*="result"], [class*="image-result"] img'
      );
      return Array.from(imgs)
        .map(img => img.src)
        .filter(s => s && s.startsWith('http'));
    });
    return imageUrls;
  },
};
