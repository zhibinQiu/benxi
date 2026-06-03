# 前端结构

> 说明书 · 第四篇 §4.1 · 代码目录 `platform-frontend/src/`

---

## 1. 技术栈

| 项 | 选型 |
|----|------|
| 框架 | Vue 3 Composition API |
| 构建 | Vite |
| UI | Naive UI |
| 路由 | Vue Router |
| HTTP | 原生 `fetch`（`api/http.js`） |

生产基础路径：`VITE_BASE_PATH=/ai/`（见 `platform-frontend/.env.example`）。

---

## 2. 目录结构

```
src/
├── api/
│   ├── http.js          # Token、api()、parseResponse
│   ├── client.js        # 聚合 re-export（兼容旧 import）
│   ├── documents.js     # 文档库 API（逐步从 client 迁出）
│   └── ...
├── views/               # 路由页面
├── layouts/
│   └── MainLayout.vue   # 侧栏、顶栏、待办、主题
├── components/          # 可复用 UI
├── composables/         # useAuth、useKnowflowEmbed 等
├── constants/           # 品牌、scope 标签、功能描述
├── router/index.js      # 路由表
├── styles/platform.css  # 全局样式
└── utils/               # navigationReturn、uiMessage、articleContent
```

---

## 3. 路由与布局

| 路径模式 | 说明 |
|----------|------|
| `/login` | 登录 |
| `/documents` | 文档中心（分级 Tab、文件夹、回收站） |
| `/documents/:id` | 文档详情 |
| `/system/functions` | 系统功能卡片墙 |
| `/system/*` | 各插件页面（翻译、对比、RAG…） |

`MainLayout` 包裹需登录页面；菜单项来自**固定一级导航**（文档中心、网站收藏等）+ **系统功能**动态卡片。

插件 `route` 必须在 `router/index.js` 注册，与后端 `FeaturePlugin.route` 一致（见 [功能插件](../platform/feature-plugins.md)）。

---

## 4. 认证与权限

`composables/useAuth.js`：

- 启动时 `GET /auth/me`
- 暴露 `user`、`permissions`、`isSystemAdmin`、`hasPerm(code)`
- 登出 `clearTokens()` + 跳转登录

按钮/菜单：`v-if="hasPerm('doc.delete')"` 等；**最终以 API 403 为准**。

---

## 5. API 层约定

- 新接口加到对应域文件（如 `api/documents.js`），勿继续膨胀 `client.js` 单文件逻辑。
- 统一 `import { api } from './http.js'`
- 列表/详情返回已是 `data` 解包后的对象

导入文档库默认 body 辅助函数：`buildImportToPersonalLibraryBody()`（`http.js`）。

---

## 6. 系统功能页

`views/SystemFunctionsView.vue`（或等价）：

1. `GET /system/features`
2. 渲染 `accessible` 卡片（`enabled` + 权限）
3. 点击 `router.push(plugin.route)`

占位功能 `enabled: false` 仍展示，带「即将推出」类 tag。

---

## 7. 知识问答嵌入

`composables/useKnowflowEmbed.js`：

1. `GET /rag/meta` 探活  
2. `GET /rag/embed-session` 取 iframe URL 与鉴权  
3. 加载 iframe；失败展示友好文案（知识服务不可用）

勿在业务页重复实现 SSO 逻辑。

---

## 8. 导航返回

`utils/navigationReturn.js`：`navigateWithReturn`、`goBackToEntry` — 用于从文档详情/订阅详情返回列表时保留筛选状态。

---

## 9. 样式与主题

- 全局：`styles/platform.css`（文档卡片、文件夹悬浮、深色模式变量）
- 功能子系统壳：`components/FeatureSubsystemShell.vue`
- 与 Naive UI 主题色对齐 `constants/platform.js`

---

## 10. 本地开发

```bash
cd platform-frontend && npm run dev -- --host 127.0.0.1 --port 40005
```

代理：开发态 `VITE_API_BASE` 为空时，Vite 可将 `/api` 代理到 8000（若 `vite.config` 已配置）；否则直连 `http://127.0.0.1:8000`。

---

## 11. 新增页面检查清单

- [ ] `router/index.js` 注册路由与 `meta`（标题、权限）
- [ ] 后端插件 `route` 与 `id` 一致
- [ ] API 方法放入 `src/api/<domain>.js`
- [ ] 错误仅用 `message.error` 或页面单一 `n-alert`
- [ ] 长列表考虑 `useBoundedScrollHeight` 等已有 composable

---

## 12. 相关文档

- [API 与约定](api-conventions.md)
- [功能插件](../platform/feature-plugins.md)
- [本地开发](../development/local-development.md)
