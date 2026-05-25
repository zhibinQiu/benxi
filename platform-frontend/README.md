# 智碳 AI平台前端

Vue 3 + Naive UI，对接 `platform` 后端 `/api/v1`。

## 开发

```bash
npm install
npm run dev
```

浏览器：http://127.0.0.1:5174（需先启动后端，见仓库根目录 `bash scripts/start_platform.sh`）。

Vite 将 `/api` 代理到 `http://127.0.0.1:8000`。

## 默认登录

- 用户名：`admin`
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
