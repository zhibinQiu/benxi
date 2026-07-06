#!/usr/bin/env node
/**
 * AI-Bridge — 免费网页 AI 桥接器
 *
 * 通过 Chrome CDP 操控 Kimi/豆包/千问/DeepSeek 等免费 Web AI，
 * 支持文本对话、生图、识图问答。
 *
 * 用法:
 *   ai-bridge chat "你的提示词"
 *   ai-bridge chat "提示词" --provider=kimi
 *   ai-bridge image "画一只猫" --provider=doubao
 *   ai-bridge ask "这是什么?" --image=./photo.jpg --provider=qwen
 *   ai-bridge --smoke
 *   ai-bridge --doctor
 */

const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright-core');

const { connectWithRetry, cdpHealthCheck } = require('./core/cdp');
const { log: _log, startTimer } = require('./core/terminal');
const { appendWithRotation } = require('./utils/telemetry');

const PREFIX = 'ai-bridge';
const log = (msg) => _log(PREFIX, msg);

// ── Provider chain ──
const { PROVIDER_CHAIN } = require('./providers/chain');
const PROVIDER_KEYS = ['kimi', 'doubao', 'qwen', 'deepseek'];

// ── Factory-built runners ──
const { createProviderRunner } = require('./factory/providerFactory');
const RUNNERS = Object.fromEntries(PROVIDER_KEYS.map(k => {
  const cfg = require(`./providers/adapters/${k}`);
  return [k, createProviderRunner(cfg)];
}));

// ── Invocation context ──
class InvocationContext {
  constructor(prompt) {
    this.telemetry = {
      timestamp: new Date().toISOString(),
      provider_used: null,
      prompt_length_chars: (prompt || '').length,
      response_length_chars: 0,
      total_ms: 0,
      mode: 'chat',
      exit_code: 0,
    };
  }

  recordTelemetry(code) {
    this.telemetry.exit_code = code;
    const dataDir = path.join(__dirname, 'data');
    const f = path.join(dataDir, 'bridge-telemetry.jsonl');
    appendWithRotation(f, JSON.stringify(this.telemetry) + '\n');
  }
}

// ── Find or reuse provider tab ──
function findProviderPage(context, provider) {
  const hosts = provider.tabHosts || (() => { try { return [new URL(provider.url).hostname]; } catch { return []; } })();
  return context.pages().find(p => {
    try {
      const pu = p.url();
      if (pu.includes('about:blank')) return false;
      return hosts.some(h => pu.includes(h));
    } catch { return false; }
  }) || null;
}

// ── Try a single provider ──
async function tryProvider(browser, providerKey, prompt, ctx, options = {}) {
  const provider = PROVIDER_CHAIN.find(p => p.key === providerKey);
  if (!provider) {
    return { success: false, reason: 'unknown_provider', error_details: { message: `未知 provider: ${providerKey}` } };
  }

  const context = browser.contexts()[0];
  if (!context) throw new Error('没有活跃的 browser context');

  const runner = RUNNERS[providerKey];
  if (!runner) {
    return { success: false, reason: 'no_runner', error_details: { message: `${providerKey} 没有 runner` } };
  }

  let page;
  let createdPage = false;

  try {
    page = findProviderPage(context, provider);
    if (page) {
      log(`复用 ${provider.name} 已有标签页`);
    } else {
      page = await context.newPage();
      createdPage = true;
    }

    // 授予剪贴板权限
    try { await context.grantPermissions(['clipboard-read', 'clipboard-write']); } catch (_) {}

    const result = await runner(page, prompt, options.timeout || 300000, ctx, {
      imagePath: options.imagePath,
      imageGen: options.imageGen,
      imageGenPrompt: options.imageGenPrompt,
    });

    // 失败时关闭我们创建的标签页
    if (!result.success && createdPage && page && !page.isClosed()) {
      try { await page.close(); } catch (_) {}
    }

    return result;
  } catch (err) {
    if (createdPage && page && !page.isClosed()) {
      try { await page.close(); } catch (_) {}
    }
    return {
      success: false,
      reason: 'error',
      error_details: { message: err.message || String(err) },
    };
  }
}

// ── Try providers in fallback chain ──
async function tryAllProviders(browser, prompt, ctx, options = {}) {
  const startFrom = options.startFrom;
  let chain = PROVIDER_CHAIN;

  if (startFrom) {
    const idx = chain.findIndex(p =>
      p.key === startFrom || p.key.includes(startFrom) || p.name.includes(startFrom)
    );
    if (idx >= 0) chain = chain.slice(idx);
  }

  const fallbackReasons = {};
  const triedProviders = [];
  const overallStart = Date.now();

  for (const provider of chain) {
    const elapsed = Date.now() - overallStart;
    const remaining = (options.timeout || 300000) - elapsed;
    if (remaining < 15000) {
      log(`${provider.name}: 总超时将到，跳过`);
      fallbackReasons[provider.key] = 'total_timeout';
      triedProviders.push(provider.key);
      break;
    }

    log(`\n▶ 尝试 ${provider.name} (预算 ${Math.round(remaining / 1000)}s)`);
    const result = await tryProvider(browser, provider.key, prompt, ctx, {
      ...options,
      timeout: Math.min(180000, remaining),
    });

    triedProviders.push(provider.key);

    if (result.success) {
      ctx.telemetry.provider_used = provider.name;
      ctx.telemetry.total_ms = Date.now() - overallStart;
      ctx.telemetry.response_length_chars = (result.response || '').length;

      if (triedProviders.length > 1) {
        log(`降级链: ${triedProviders.join(' → ')}`);
      }
      return result;
    }

    fallbackReasons[provider.key] = result.reason;
    log(`✗ ${provider.name}: ${result.reason}${result.error_details ? ' - ' + result.error_details.message : ''}`);
  }

  return {
    success: false,
    reasons: fallbackReasons,
    triedProviders,
  };
}

// ── Smoke test ──
async function smokeTest(browser) {
  log('运行环境检查...');
  const context = browser.contexts()[0];
  for (const provider of PROVIDER_CHAIN) {
    let page;
    try {
      if (findProviderPage(context, provider)) {
        log(`  ${provider.name}: ✅ 可达 (现有标签)`);
        continue;
      }
      page = await context.newPage();
      await page.goto(provider.url, { waitUntil: 'domcontentloaded', timeout: 20000 });
      const url = page.url();
      const isAuth = provider.authDomains.some(d => url.includes(d));
      if (isAuth) {
        log(`  ${provider.name}: ⚠ 可达但需登录 (${url.substring(0, 50)})`);
      } else {
        log(`  ${provider.name}: ✅ 可达`);
      }
    } catch (err) {
      log(`  ${provider.name}: ❌ 不可达 — ${err.message}`);
    } finally {
      if (page && !page.isClosed()) try { await page.close(); } catch (_) {}
    }
  }
  log('环境检查完成');
}

// ── MAIN ──
async function main() {
  const args = process.argv.slice(2);

  // --doctor
  if (args.includes('--doctor')) {
    return cdpHealthCheck(true, log);
  }

  // --smoke
  if (args.includes('--smoke')) {
    let browser;
    try {
      browser = await connectWithRetry(chromium);
    } catch (err) {
      log(`FATAL: 无法连接 Chrome: ${err.message}`);
      process.exit(1);
    }
    try {
      await smokeTest(browser);
    } finally {
      if (browser) try { await browser.close(); } catch (_) {}
    }
    process.exit(0);
  }

  // Parse mode
  let mode = 'chat'; // chat | image | ask
  let prompt = '';
  let provider = null;
  let imagePath = null;
  let timeout = 300000;
  let keepTabs = true;

  const remaining = [];
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === 'chat') { mode = 'chat'; }
    else if (a === 'image' || a === 'img') { mode = 'image'; }
    else if (a === 'ask') { mode = 'ask'; }
    else if (a.startsWith('--provider=')) { provider = a.split('=')[1]; }
    else if (a.startsWith('--from=')) { provider = a.split('=')[1]; }
    else if (a.startsWith('--image=')) { imagePath = a.split('=')[1]; }
    else if (a.startsWith('--timeout=')) { const v = parseInt(a.split('=')[1], 10); if (!isNaN(v) && v > 0) timeout = v < 10000 ? v * 1000 : v; }
    else if (a === '--keep-tabs') { keepTabs = true; }
    else if (a === '--close' || a === '--close-browser') { keepTabs = false; }
    else if (!a.startsWith('--')) { remaining.push(a); }
  }

  prompt = remaining.join(' ').trim();

  // If no prompt and stdin is piped
  if (!prompt && !process.stdin.isTTY) {
    const chunks = [];
    process.stdin.setEncoding('utf-8');
    for await (const chunk of process.stdin) chunks.push(chunk);
    prompt = chunks.join('').trim();
  }

  if (!prompt) {
    console.error(`
AI-Bridge — 免费网页 AI 桥接器

用法:
  ai-bridge chat "你的问题" [--provider=kimi|doubao|qwen|deepseek]
  ai-bridge image "画图描述" [--provider=doubao|qwen]
  ai-bridge ask "关于图片的问题" --image=./photo.jpg [--provider=kimi|doubao|qwen|deepseek]

  ai-bridge --smoke      环境检查
  ai-bridge --doctor     Chrome CDP 连通性检查

示例:
  ai-bridge chat "用 Python 写一个快速排序"
  ai-bridge image "一只可爱的橘猫" --provider=doubao
  ai-bridge ask "这张图里有几个人?" --image=./group.jpg --provider=qwen
    `.trim());
    process.exit(1);
  }

  const ctx = new InvocationContext(prompt);
  ctx.telemetry.mode = mode;

  log(`模式: ${mode}`);
  if (mode === 'image') log('🎨 图片生成模式');
  if (mode === 'ask') log(`🖼️ 识图问答模式 (图片: ${imagePath || '未指定'})`);

  // Connect to Chrome
  let browser;
  try {
    browser = await connectWithRetry(chromium);
  } catch (err) {
    log(`FATAL: 无法连接 Chrome CDP: ${err.message}`);
    log('请确保 Chrome 调试模式已启动: bash packages/ai-bridge/scripts/start-chrome.sh');
    ctx.recordTelemetry(1);
    process.exit(1);
  }

  try {
    let result;

    if (provider) {
      // 指定 provider
      log(`指定使用: ${provider}`);
      result = await tryProvider(browser, provider.toLowerCase(), prompt, ctx, {
        timeout,
        imagePath: mode === 'ask' ? imagePath : undefined,
        imageGen: mode === 'image',
        imageGenPrompt: prompt,
      });
    } else {
      // 自动 fallback
      const options = {
        timeout,
        startFrom: null,
        imagePath: mode === 'ask' ? imagePath : undefined,
        imageGen: mode === 'image',
        imageGenPrompt: prompt,
      };

      // 生图优先用支持生图的 provider
      if (mode === 'image') {
        options.startFrom = 'doubao'; // 豆包生图能力强
      }

      result = await tryAllProviders(browser, prompt, ctx, options);
    }

    if (result.success) {
      // 输出回复
      console.log(result.response);

      // 如果有图片 URL，输出
      if (result.imageUrls && result.imageUrls.length > 0) {
        console.error(`\n[ai-bridge] 🎨 生成 ${result.imageUrls.length} 张图片:`);
        result.imageUrls.forEach((url, i) => {
          console.error(`[ai-bridge]   图 ${i + 1}: ${url}`);
        });
      }

      ctx.recordTelemetry(0);
      process.exit(0);
    }

    // 处理失败
    const reasons = result.reasons || { [provider || 'unknown']: result.reason || 'error' };
    const reasonVals = Object.values(reasons).map(r => typeof r === 'string' ? r : r.reason || '');
    const allAuth = reasonVals.length > 0 && reasonVals.every(r => r.includes('auth'));
    const allQuota = reasonVals.length > 0 && reasonVals.every(r => r === 'quota');
    const hasTimeout = reasonVals.some(r => r.includes('timeout'));

    if (allAuth) {
      log('所有 provider 需要登录，请在 Chrome 中先登录相关 AI 网站');
      ctx.recordTelemetry(2);
      process.exit(2);
    }
    if (allQuota) {
      log('所有 provider 配额已耗尽');
      ctx.recordTelemetry(5);
      process.exit(5);
    }
    if (hasTimeout) {
      log('所有 provider 超时');
      ctx.recordTelemetry(10);
      process.exit(10);
    }
    log(`所有 provider 不可用: ${JSON.stringify(reasons)}`);
    ctx.recordTelemetry(9);
    process.exit(9);

  } catch (err) {
    log(`FATAL: ${err.message}`);
    ctx.recordTelemetry(4);
    process.exit(4);
  } finally {
    // 绝不关闭 Chrome 浏览器（我们是客人）
  }
}

if (require.main === module) {
  main().catch(e => {
    process.stderr.write(`[ai-bridge] 未处理错误: ${e.message}\n`);
    process.exit(4);
  });
}

module.exports = { tryProvider, tryAllProviders, PROVIDER_CHAIN };
