---
name: web-ai-bridge
description: 通过 Chrome CDP 操控免费网页 AI（Kimi/豆包/千问/DeepSeek）执行文本对话、生图、识图问答等子任务。使用本项目 packages/ai-bridge 中的 Node.js 工具实现，底层依赖 playwright-core + Chrome CDP。
---

# Web AI Bridge — 免费网页 AI 子任务执行器

通过接管本地 Chrome 浏览器，操控网页版 AI（Kimi/豆包/千问/DeepSeek），无需付费 API key 即可执行子任务。

## 触发场景

当用户需要以下能力时使用本 Skill：
- 使用免费网页 AI 执行子任务（代码生成、文案、翻译、分析）
- 文字生成图片（目前支持 豆包、通义千问）
- 上传图片并进行问答（识图，支持 Kimi/DeepSeek/豆包/千问）
- 需要一个可降级的 AI 后备方案（自动 fallback 到下一个可用 provider）

## 环境准备

### 1. Chrome 调试模式

```bash
# 启动 Chrome 调试模式（端口 9222）
bash packages/ai-bridge/scripts/start-chrome.sh
```

### 2. 登录 AI 网站

在启动的 Chrome 中手动登录以下网站（只需一次，登录态保存在 Chrome profile 中）：

| Provider | 登录地址 | 能力 |
|----------|---------|------|
| Kimi | https://kimi.moonshot.cn/ | 文本对话、识图 |
| 豆包 | https://www.doubao.com/chat/ | 文本对话、生图、识图 |
| 通义千问 | https://tongyi.aliyun.com/qianwen/ | 文本对话、生图、识图 |
| DeepSeek | https://chat.deepseek.com/ | 文本对话、识图 |

### 3. 安装依赖

```bash
cd packages/ai-bridge && npm install
```

## 使用方式

所有子任务通过 `node packages/ai-bridge/index.js` 执行，自动 fallback 链。

### 文本对话

```bash
# 自动选择可用 provider
node packages/ai-bridge/index.js chat "用 Python 写一个快速排序算法"

# 指定 provider
node packages/ai-bridge/index.js chat "翻译这段话成英文" --provider=kimi
```

### 文字生图

```bash
# 图片生成（自动选支持生图的 provider）
node packages/ai-bridge/index.js image "一只可爱的橘猫，坐在窗台上，阳光洒进来"

# 指定生图 provider
node packages/ai-bridge/index.js image "水墨山水画" --provider=doubao
```

### 识图问答

```bash
# 上传图片并提问
node packages/ai-bridge/index.js ask "这张图里有什么?" --image=/path/to/photo.jpg

# 指定识图 provider
node packages/ai-bridge/index.js ask "图中的人是谁?" --image=./photo.jpg --provider=kimi
```

### 环境检查

```bash
# 检查 Chrome CDP 是否可达
node packages/ai-bridge/index.js --doctor

# 检查所有 provider 可达性
node packages/ai-bridge/index.js --smoke
```

## 代码集成

### 在 JS/TS 中直接调用

```javascript
const { chromium } = require('playwright-core');
const { tryProvider, tryAllProviders } = require('packages/ai-bridge');

async function askAI(prompt) {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
  const ctx = { telemetry: {} };
  const result = await tryAllProviders(browser, prompt, ctx, { timeout: 120000 });
  if (result.success) return result.response;
  throw new Error(`AI 调用失败: ${result.reason}`);
}
```

### CLI 模式在子进程中调用

```javascript
const { execSync } = require('child_process');

const result = execSync(
  'node packages/ai-bridge/index.js chat "用 Python 写排序"',
  { encoding: 'utf-8', timeout: 120000 }
);
console.log(result);
```

## 架构说明

```
packages/ai-bridge/
├── index.js                    # CLI 入口 + fallback 编排器
├── core/
│   ├── cdp.js                  # Chrome CDP 连接 + 健康检查
│   ├── errors.js               # 结构化错误处理
│   └── terminal.js             # 终端 spinner/logging
├── factory/
│   └── providerFactory.js      # 10 步 config-driven 流水线
├── providers/
│   ├── chain.js                # Provider 优先级链
│   └── adapters/
│       ├── kimi.js             # Kimi 适配器（文本+识图）
│       ├── doubao.js           # 豆包适配器（文本+识图+生图）
│       ├── qwen.js             # 千问适配器（文本+识图+生图）
│       └── deepseek.js         # DeepSeek 适配器（文本+识图）
└── scripts/
    ├── start-chrome.sh         # Chrome 调试模式启动脚本
    └── env.example             # 环境变量示例
```

### Fallback 链

```
通义千问 → Kimi → 豆包 → DeepSeek
```

### 10 步流水线

1. Navigate（导航到网页）
2. Auth check（检查登录）
3. Quota check（检查配额）
4. Overlay dismiss（关弹窗）
5. Pre-input hook（前置钩子，如新建会话）
6. Find editor（找输入框）
7. Input text（输入提示词）
8. Click send（发送）
9. Wait response（等回复）
10. Extract（提取回复内容）

## 重要提示

- **系统 Chrome + 登录态**：必须使用系统 Chrome（非 Playwright 内置），且需先手动登录 AI 网站
- **不关闭用户浏览器**：脚本绝不调用 `browser.close()`，因为它是 CDP 连接到用户的已有浏览器
- **标签页复用**：会复用已有同 provider 标签页而非重复创建
- **代理**：中国大陆用户需配置 `PROXY_SERVER` 环境变量
- **生图限制**：生图质量取决于网页版 provider 的能力，推荐使用 豆包 或 通义千问
