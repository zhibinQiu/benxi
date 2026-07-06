const http = require('http');

const DEFAULT_CDP_PORT = process.env.CDP_PORT || '9222';
const CDP_URL = `http://127.0.0.1:${DEFAULT_CDP_PORT}`;

async function connectWithRetry(chromium, cdpUrl, retries = 3, onLog = () => {}) {
  const url = cdpUrl || CDP_URL;
  for (let i = 1; i <= retries; i++) {
    try {
      onLog(`连接 Chrome CDP (尝试 ${i}/${retries})...`);
      const browser = await chromium.connectOverCDP(url);
      browser.on('disconnected', () => {
        onLog('警告: Chrome CDP 连接已断开');
      });
      return browser;
    } catch (err) {
      if (i === retries) throw err;
      await new Promise(r => setTimeout(r, 2000));
    }
  }
}

async function cdpHealthCheck(exitOnFail = true, onLog = console.error) {
  try {
    const res = await new Promise((resolve, reject) => {
      const req = http.get(`${CDP_URL}/json/version`, (res) => {
        let data = '';
        res.on('data', c => data += c);
        res.on('end', () => resolve({ ok: true, data }));
      });
      req.on('error', reject);
      req.setTimeout(5000, () => { req.destroy(); reject(new Error('CDP 超时')); });
    });
    onLog(`Chrome CDP 可达: ${JSON.stringify(JSON.parse(res.data).Browser)}`);
    return true;
  } catch (e) {
    onLog(`Chrome CDP 不可达 (${CDP_URL})`);
    onLog('请先启动 Chrome 调试模式: bash packages/ai-bridge/scripts/start-chrome.sh');
    if (exitOnFail) process.exit(1);
    return false;
  }
}

module.exports = { connectWithRetry, cdpHealthCheck, CDP_URL };
