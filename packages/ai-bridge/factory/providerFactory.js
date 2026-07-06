/**
 * Provider Factory — 可配置的 10 步流水线
 *
 * 所有 provider 的差异通过 config 表达（选择器、钩子、超时等），
 * 而非为每个 provider 复制粘贴相似的 tryXxx() 函数。
 *
 * 10 步流程:
 *   1. Navigate     → 导航到 AI 网页
 *   2. Auth check   → 检查是否需要登录
 *   3. Quota check  → 检查配额是否耗尽
 *   4. Overlay      → 关掉弹窗/公告
 *   5. Pre-input    → 前置钩子（如切换模型）
 *   6. Find editor  → 找到输入框
 *   7. Input text   → 输入用户提示
 *   8. Send         → 点击发送按钮
 *   9. Wait response → 等 AI 回复完成
 *   10. Extract     → 提取回复内容
 *
 * 图片能力:
 *   - imageUpload: 在 input 前通过 CDP 设置文件输入
 *   - imageGenWait: 生图后等待图片元素出现并下载
 */

const { ProviderError, classifyError, STAGES, REASONS } = require('../core/errors');

// ── 公共中文限流模式 ──
const COMMON_CN_QUOTA_PATTERNS = [
  /额度.*(?:已|用).*(?:完|尽|满)/i,
  /quota\s*(?:exceeded|limit)/i,
  /次数.*(?:已|用).*(?:完|尽)/i,
  /请.*(?:充值|升级|续费)/i,
  /rate\s*limit/i,
  /too\s*many\s*requests/i,
];

// ── 公共可关闭弹窗模式 ──
const COMMON_DISMISS_PATTERNS = [
  /新功能/i, /公告/i, /欢迎/i, /更新.*(?:说明|日志)/i,
  /what'?s\s*new/i, /new\s*feature/i, /welcome/i,
  /try\s*(?:the\s*)?new/i, /introducing/i,
];

// ── 原子操作 ──

async function findEditableElement(page, selectors, validateFn) {
  for (const sel of selectors) {
    try {
      const el = await page.$(sel);
      if (!el) continue;
      if (validateFn) {
        const valid = await validateFn(el);
        if (!valid) continue;
      }
      return el;
    } catch (_) { continue; }
  }
  return null;
}

async function inputViaClipboard(page, editor, prompt) {
  try {
    await editor.evaluate(el => {
      el.focus();
      document.execCommand('selectall');
    });
    await page.evaluate(text => {
      navigator.clipboard.writeText(text);
    }, prompt);
    await editor.evaluate(() => document.execCommand('paste'));
    return true;
  } catch { return false; }
}

async function inputViaKeyboard(page, editor, prompt, { chunkSize = 150, yieldMs = 40 } = {}) {
  try {
    await editor.click();
    await editor.fill('');
    for (let i = 0; i < prompt.length; i += chunkSize) {
      const chunk = prompt.slice(i, i + chunkSize);
      await page.keyboard.type(chunk, { delay: 10 });
      await new Promise(r => setTimeout(r, yieldMs));
    }
    return true;
  } catch { return false; }
}

async function defaultInput(page, editor, prompt) {
  if (prompt.length <= 500) {
    // 短文本: clipboard 粘贴最快
    if (await inputViaClipboard(page, editor, prompt)) return true;
  }
  return await inputViaKeyboard(page, editor, prompt);
}

async function clickSend(page, editor, sendSelectors, fallbackKey) {
  for (const sel of sendSelectors) {
    try {
      const btn = await page.$(sel);
      if (btn) {
        const disabled = await btn.evaluate(el => el.disabled || el.getAttribute('aria-disabled') === 'true' || el.classList.contains('disabled'));
        if (!disabled) {
          await btn.click();
          return true;
        }
      }
    } catch (_) {}
  }
  // 兜底: 键盘快捷键
  if (fallbackKey) {
    await page.keyboard.press(fallbackKey);
    return true;
  }
  return false;
}

async function dismissOverlays(page, dismissPatterns) {
  // 尝试找关闭按钮点击
  const closeSelectors = [
    'button[aria-label*="关闭"]', 'button[aria-label*="Close"]', 'button[aria-label*="Dismiss"]',
    '.close-btn', '.dismiss-btn', '[class*="close"]', '[class*="dismiss"]',
    'svg[aria-label*="close"]', 'svg[aria-label*="Close"]',
  ];
  for (const sel of closeSelectors) {
    try {
      const btn = await page.$(sel);
      if (btn && await btn.isVisible()) {
        await btn.click();
        await new Promise(r => setTimeout(r, 500));
      }
    } catch (_) {}
  }
}

async function waitForStopButton(page, stopSelectors, stopWaitMode, timeoutMs, stopBtnExtensionMs) {
  if (!stopSelectors || stopSelectors.length === 0) return true;
  const start = Date.now();
  const baseTimeout = timeoutMs + (stopBtnExtensionMs || 0);

  while (Date.now() - start < baseTimeout) {
    let stopBtn = null;
    for (const sel of stopSelectors) {
      stopBtn = await page.$(sel);
      if (stopBtn) break;
    }
    if (!stopBtn) return true; // 停止按钮消失 → 回复完成

    // 检查模式
    if (stopWaitMode === 'detached') {
      // detached: 按钮从 DOM 完全移除
      // 我们继续 polling 直到 DOM 中没有
    } else {
      // hidden: 按钮存在但不可见
      try {
        const visible = await stopBtn.isVisible();
        if (!visible) return true;
      } catch { return true; }
    }
    await new Promise(r => setTimeout(r, 1000));
  }
  return false; // 超时
}

async function extractResponse(page, responseSelectors, minLength) {
  for (const sel of responseSelectors) {
    try {
      const el = await page.$(sel);
      if (!el) continue;
      // 获取最后一个匹配元素（最新回复）
      const elements = await page.$$(sel);
      const lastEl = elements[elements.length - 1];
      if (!lastEl) continue;
      const text = await lastEl.evaluate(el => el.textContent || el.innerText || '');
      if (text.trim().length >= (minLength || 10)) {
        return text.trim();
      }
    } catch (_) {}
  }
  return null;
}

async function waitForCompletion(page, config, timeoutMs) {
  const { stabilityWindow = 10000, pollInterval = 2000, completionAnchor, stillGeneratingCheck, stopSelectors, stopWaitMode, stopBtnExtensionMs, responseSelectors, minResponseLength } = config;
  const overallStart = Date.now();
  let lastText = '';
  let stableStart = null;
  const effectiveTimeout = timeoutMs + (stopBtnExtensionMs || 0);

  while (Date.now() - overallStart < effectiveTimeout) {
    // 检查停止按钮
    if (stopSelectors && stopSelectors.length > 0) {
      let stopExists = false;
      for (const sel of stopSelectors) {
        const btn = await page.$(sel);
        if (btn) { try { stopExists = await btn.isVisible(); } catch { stopExists = false; } if (stopExists) break; }
      }
      if (!stopExists) {
        // 停止按钮消失 → 提取文本
        const text = await extractResponse(page, responseSelectors, minResponseLength);
        if (text) return { done: true, text, timedOut: false };
      }
    }

    // completionAnchor: 明确的"完成"信号
    if (completionAnchor) {
      const anchors = Array.isArray(completionAnchor) ? completionAnchor : [completionAnchor];
      for (const anchor of anchors) {
        try {
          const el = await page.$(anchor);
          if (el && await el.isVisible()) {
            const text = await extractResponse(page, responseSelectors, minResponseLength);
            if (text) return { done: true, text, timedOut: false };
          }
        } catch {}
      }
    }

    // 稳定性检测
    const currentText = await extractResponse(page, responseSelectors, 1);
    if (currentText) {
      if (currentText === lastText) {
        if (!stableStart) stableStart = Date.now();
        else if (Date.now() - stableStart >= stabilityWindow) {
          // 检查 stillGeneratingCheck
          if (stillGeneratingCheck) {
            const stillGoing = await stillGeneratingCheck(page);
            if (!stillGoing) {
              return { done: true, text: currentText, timedOut: false };
            }
            stableStart = null; // 重置，继续等待
          } else {
            return { done: true, text: currentText, timedOut: false };
          }
        }
      } else {
        lastText = currentText;
        stableStart = null;
      }
    }

    await new Promise(r => setTimeout(r, pollInterval));
  }

  // 超时 — 尝试提取已有内容
  const text = await extractResponse(page, responseSelectors, 1);
  return { done: false, text: text || '', timedOut: true };
}

// ── 默认值 ──
const DEFAULTS = {
  navTimeout: 60000,
  navWaitUntil: 'domcontentloaded',
  navPostDelay: 0,
  stopWaitMode: 'hidden',
  stopBtnExtensionMs: 0,
  completionAnchor: null,
  stillGeneratingCheck: null,
  responseSelectorTimeout: 60000,
  stabilityWindow: 10000,
  pollInterval: 2000,
  minResponseLength: 10,
  input: defaultInput,
  dismissPatterns: [],
  supportsImageUpload: false,
  supportsImageGen: false,
};

// ── 工厂函数: 10 步流水线 ──
function createProviderRunner(cfg) {
  const C = { ...DEFAULTS, ...cfg };

  return async function run(page, prompt, timeoutMs, ctx, options = {}) {
    const provStart = Date.now();
    const log = (msg) => { if (ctx && ctx.log) ctx.log(`[${C.key}] ${msg}`); };
    let timer = { stop() {} };

    try {
      // ── Step 1: Navigate ──
      timer = require('../core/terminal').startTimer('ai-bridge', `${C.name} 导航`);
      log('正在导航到 ' + C.url);
      await page.goto(C.url, { waitUntil: C.navWaitUntil, timeout: C.navTimeout });
      if (C.navPostDelay > 0) await new Promise(r => setTimeout(r, C.navPostDelay));
      timer.stop();

      // ── Step 1.5: 图片上传（如需要） ──
      if (options.imagePath && C.supportsImageUpload) {
        timer = require('../core/terminal').startTimer('ai-bridge', `${C.name} 上传图片`);
        log('正在上传图片: ' + options.imagePath);
        if (typeof C.uploadImage === 'function') {
          const uploadOk = await C.uploadImage(page, options.imagePath, log);
          if (!uploadOk) {
            timer.stop();
            return { success: false, reason: 'image_upload_failed', error_details: { message: '图片上传失败' } };
          }
        } else {
          // 默认: 查找文件输入并设置
          try {
            const [fileChooser] = await Promise.all([
              page.waitForEvent('filechooser', { timeout: 10000 }),
              page.click('[type="file"], input[accept*="image"], [class*="upload"]'),
            ]);
            await fileChooser.setFiles(options.imagePath);
            await new Promise(r => setTimeout(r, 2000));
          } catch (e) {
            log('图片上传失败: ' + e.message);
          }
        }
        timer.stop();
      }

      // ── Step 2: Auth check ──
      const currentUrl = page.url();
      const needsAuth = C.authDomains.some(d => currentUrl.includes(d));
      if (needsAuth) {
        log('⛔ 需要登录，跳过');
        return { success: false, reason: 'auth', error_details: { message: `${C.name} 需要登录` } };
      }

      // ── Step 3: Quota check ──
      if (C.quotaPatterns && C.quotaPatterns.length > 0) {
        const body = await page.evaluate(() => document.body.innerText || '').catch(() => '');
        const isQuotaExceeded = C.quotaPatterns.some(p => p.test(body));
        if (isQuotaExceeded) {
          log('⛔ 配额耗尽，跳过');
          return { success: false, reason: 'quota', error_details: { message: `${C.name} 配额已耗尽` } };
        }
      }

      // ── Step 3.5: 弹窗处理 ──
      if (C.dismissPatterns && C.dismissPatterns.length > 0) {
        await dismissOverlays(page, C.dismissPatterns);
      }

      // ── Step 4: Pre-input hook ──
      if (C.preInputHook) {
        timer = require('../core/terminal').startTimer('ai-bridge', `${C.name} pre-hook`);
        await C.preInputHook(page, C, log);
        timer.stop();
      }

      // ── Step 5-6: Find editor + Input text ──
      timer = require('../core/terminal').startTimer('ai-bridge', `${C.name} 输入`);
      let editor = null;
      if (typeof C.findEditor === 'function') {
        editor = await C.findEditor(page, C, log);
      } else {
        editor = await findEditableElement(page, C.editorSelectors, C.validateEditor);
      }
      if (!editor) {
        timer.stop();
        log('⛔ 找不到输入框');
        return { success: false, reason: 'error', error_details: { message: '找不到输入框' } };
      }

      // 图片生成模式
      if (options.imageGen && C.supportsImageGen) {
        log('🎨 图片生成模式');
        const genPrompt = options.imageGenPrompt || prompt;
        if (typeof C.inputImageGenPrompt === 'function') {
          await C.inputImageGenPrompt(page, editor, genPrompt, C);
        } else {
          await defaultInput(page, editor, genPrompt);
        }
      } else {
        await C.input(page, editor, prompt, C);
      }
      timer.stop();

      // ── Step 7: Send ──
      timer = require('../core/terminal').startTimer('ai-bridge', `${C.name} 发送`);
      let sendOk = false;
      if (C.customSend) {
        sendOk = await C.customSend(page, editor, C);
      } else {
        sendOk = await clickSend(page, editor, C.sendSelectors, C.sendFallback);
      }
      if (!sendOk) {
        timer.stop();
        log('⛔ 无法发送');
        return { success: false, reason: 'error', error_details: { message: '发送失败' } };
      }
      timer.stop();

      // ── Step 8: Wait for response ──
      timer = require('../core/terminal').startTimer('ai-bridge', `${C.name} 等待回复`);
      log('⏳ 等待 AI 回复...');
      const result = await waitForCompletion(page, C, timeoutMs - (Date.now() - provStart));
      timer.stop();

      if (result.timedOut && !result.text) {
        return { success: false, reason: 'timeout', error_details: { message: `${C.name} 回复超时` } };
      }

      // ── Step 8.5: 图片生成完成 — 提取图片 ──
      let imageUrls = [];
      if (options.imageGen && C.supportsImageGen) {
        timer = require('../core/terminal').startTimer('ai-bridge', `${C.name} 提取图片`);
        if (typeof C.extractImages === 'function') {
          imageUrls = await C.extractImages(page, C, log);
        } else {
          // 默认: 提取所有 img 标签
          imageUrls = await page.evaluate(() => {
            const imgs = document.querySelectorAll('img[src*="blob:"], img[src*="data:"], img[src*="https://"]');
            return Array.from(imgs).map(img => img.src).filter(s => s && !s.includes('data:image/gif'));
          });
        }
        log(`提取到 ${imageUrls.length} 张图片`);
        timer.stop();
      }

      // ── Step 9: Post-process ──
      let response = result.text || '';
      if (response && C.postResponseHook) {
        response = await C.postResponseHook(page, response, C);
      }

      // ── Step 10: Success ──
      ctx.telemetry.provider_used = C.name;
      const elapsed = Date.now() - provStart;
      if (ctx.telemetry) {
        ctx.telemetry.per_provider_ms = ctx.telemetry.per_provider_ms || {};
        ctx.telemetry.per_provider_ms[C.key] = elapsed;
      }
      log(`✓ ${C.name}: ${response.length} chars, ${elapsed}ms`);

      const resp = { success: true, response, provider: C.name };
      if (imageUrls.length > 0) resp.imageUrls = imageUrls;
      return resp;

    } catch (err) {
      timer.stop();
      const pe = new ProviderError(err, { stage: 'unknown', provider: C.key, reason: REASONS.ERROR });
      log(`✗ ${C.name}: ${err.message}`);
      return pe.toResult();
    }
  };
}

module.exports = {
  createProviderRunner,
  COMMON_CN_QUOTA_PATTERNS,
  COMMON_DISMISS_PATTERNS,
  findEditableElement,
  defaultInput,
  clickSend,
  extractResponse,
  waitForCompletion,
};
