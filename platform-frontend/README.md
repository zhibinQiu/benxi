# 智碳平台AI系统前端

Vue 3 + Naive UI，对接 `platform` 后端 `/api/v1`。

## API 模块（按域拆分）

| 文件 | 职责 |
|------|------|
| `src/api/http.js` | Token、`api()`、错误解析 |
| `src/api/auth.js` | 登录、用户、角色 |
| `src/api/documents.js` | 文档库 |
| `src/api/rag.js` | 知识问答 / KnowFlow 嵌入 |
| `src/api/client.js` | 聚合 re-export（兼容旧 import） |

新页面优先 `import { fetchDocument } from "../api/documents"`，避免继续增大 `client.js`。

## 开发

```bash
npm install
npm run dev
```

浏览器：http://127.0.0.1:40005/ai/（需先启动后端：`bash scripts/zhitan.sh`）。

Vite 将 `/api` 代理到 `http://127.0.0.1:8000`。

## 默认登录

- 系统管理员手机号：`15963564658`
- 密码：`admin123`

## 主要路由

| 路由 | 说明 |
|------|------|
| `/login` | 登录 |
| `/documents` | 文档列表与上传 |
| `/system/translate` | PDF 翻译 |
| `/jobs` | 异步任务 |
| `/notifications` | 站内消息 |
| `/admin/users` | 用户管理 |
