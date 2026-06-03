# API 与约定

> 说明书 · 第三篇 §3.1 · 实现以 `platform/app/api/`、`app/schemas/`、`app/core/exceptions.py` 为准。

---

## 1. 路由与前缀

| 项 | 约定 |
|----|------|
| 统一前缀 | `/api/v1` |
| 网关对外 | 可配置 `API_PUBLIC_PATH_PREFIX=/ai`，完整路径如 `/ai/api/v1` |
| Swagger | `http://127.0.0.1:8000/docs`（本地） |
| 插件路由 | `features/registry.py` → `mount_routers(app)` 挂载到同一 app |

核心路由在 `app/main.py` 显式 `include_router`：`auth`、`users`、`documents`、`jobs`、`system` 等；业务能力多在 `app/features/builtin/*` 自带 `router`。

---

## 2. 统一响应体

成功响应使用 Pydantic 泛型 `ApiResponse[T]`：

```json
{
  "code": 0,
  "message": "ok",
  "data": { ... }
}
```

定义：`app/schemas/common.py`。

路由返回示例：

```python
return ApiResponse(data=SomeOut.model_validate(entity))
```

业务错误使用 `AppError`（`app/core/exceptions.py`），由全局 handler 转为：

```json
{
  "code": 400,
  "message": "中文说明"
}
```

| HTTP | 场景 |
|------|------|
| 200 + `code!=0` | 少见；多数业务错误仍 200 或 4xx |
| 400/403/404 | `AppError` 对应状态码 |
| 422 | FastAPI 校验失败，`detail` 为字段数组 |
| 500 | 未捕获异常，message 为通用「服务器内部错误…」 |

---

## 3. 鉴权依赖

| Depends | 文件 | 用途 |
|---------|------|------|
| `get_current_user` | `app/api/deps.py` | JWT Bearer，注入 `User` |
| `get_db` | `app/database.py` | SQLAlchemy Session |
| `require_permission("doc.read")` | `deps.py` | RBAC 功能权限 |
| `require_feature("compare")` | `deps.py` | 按插件 id 校验 `feature.*` |

登录：`POST /api/v1/auth/login`，body 字段 `account`（手机号或用户名）+ `password`。  
刷新与注销见 `app/api/auth.py`。

前端 Token：`localStorage` 键 `platform_access_token`，请求头 `Authorization: Bearer …`（`platform-frontend/src/api/http.js`）。

---

## 4. 分页

查询参数常用 `page`、`page_size`（`PageParams`，默认 1/20，最大 page_size 100）。  
列表返回 `PageResult`：`items`、`total`、`page`、`page_size`。

---

## 5. 文档相关 API 索引

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/documents` | 列表/创建 |
| GET/PATCH/DELETE | `/documents/{id}` | 详情/更新/软删 |
| POST | `/documents/{id}/upload/prepare` | MinIO 预签名 |
| POST | `/documents/{id}/upload/complete` | 完成上传 |
| GET | `/documents/{id}/download` | 下载当前版本 |
| POST | `/documents/{id}/sync-knowflow` | 强制同步知识库 |
| GET/POST/DELETE | `/documents/{id}/permissions/...` | 分享与 deny |

完整列表以 Swagger 为准。

---

## 6. 前端请求约定

```javascript
// platform-frontend/src/api/http.js
export async function api(path, options) { ... }
```

| 行为 | 实现 |
|------|------|
| Base URL | `VITE_API_BASE`，生产常 `/ai` |
| 成功 | `json.code === 0` 时返回 `json.data` |
| 失败 | `throw new Error(中文 message)` |
| 422 | `formatApiDetail` 转字段中文 |
| 500 文案 | `sanitizeUserFacingMessage` 避免暴露内部栈 |

**UX 约定**：同一操作只弹一条 `message`；页面 `n-alert` 与 toast 不重复（`utils/uiMessage.js`）。

---

## 7. 新增 API 检查清单

- [ ] 路由加 `Depends(get_current_user)`（除公开接口）
- [ ] 文档类接口调用 `can_access_document` / `can_read_document` 等
- [ ] 返回 `ApiResponse`，错误 `raise AppError` 或 `HTTPException`
- [ ] Schema 放在 `app/schemas/`，勿在路由内嵌大 dict
- [ ] 插件 API 加 `require_feature("plugin_id")`
- [ ] 前端在 `src/api/` 域文件增加方法，经 `client.js` re-export

---

## 8. 相关文档

- [应用服务与域](backend-implementation.md)
- [权限模型](../platform/permission-model.md)
- [平台架构与运维](../development/platform-architecture.md) §9
