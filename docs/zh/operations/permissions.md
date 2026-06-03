# 权限与账户

## 认证

- **JWT** Bearer（`Authorization: Bearer <token>`）
- 登录：`POST /api/v1/auth/login`（手机号 + 密码）
- 注册：`POST /api/v1/auth/register`（可配置 `allow_public_register`）
- Bootstrap 管理员：`BOOTSTRAP_ADMIN_*` 环境变量，首次启动 seed

## RBAC

| 实体 | 说明 |
|------|------|
| User | 用户；可属多部门 |
| Role | 角色：`sys_admin`、`member` 等 |
| Permission | 权限码，如 `admin.users`、`feature.rag_qa` |
| UserRole / RolePermission | 多对多 |

**超级用户：** 拥有 `sys_admin` 角色的用户跳过权限检查。

### 功能权限

每个 `FeaturePlugin` 注册 `permission_code`（如 `feature.data_analysis`），启动时写入 DB 并授予默认角色。

前端路由 `meta.perm` 与侧栏菜单按 `hasPerm()` 过滤。

### 管理权限

| 权限码 | 能力 |
|--------|------|
| `admin.users` | 用户管理 |
| `admin.departments` | 部门 |
| `admin.roles` | 角色 |
| `admin.audit` | 审计日志 |
| `admin.settings` | 模型配置等 |

## 文档分级（Scope）

| Scope | 含义 | RBAC 前缀 |
|-------|------|-----------|
| company | 全公司 | `doc.company.*` |
| department | 本部门 | `doc.department.*` |
| team | 团队 | `doc.team.*` |
| personal | 个人 | `doc.personal.*` |

文档另有 **ACL**（用户/部门/角色级 `visible/query/edit/full`）与 **deny** 规则。

## KnowFlow 账号映射

- 模式 `ragflow_account_mode=mapped`：每平台用户独立 RAGFlow 账号与 dataset
- 命名：`zt-platform-{user_id}`、`zt-personal-*`、`zt-dept-*` 等
- SSO：`rag/embed-session` 自动 provision + 返回 `auth` query
- 系统管理员可配置 `ragflow_grant_global_admin`

详见 [权限模型](../platform/permission-model.md)（细节不变，路径仍有效）。

## 审计

- 敏感操作写 `audit_logs`
- 监控页需 `admin.audit`

## 生产建议

- 修改默认 `JWT_SECRET`、MinIO 密码、MySQL/ES 密码
- 关闭公开注册或限制网络
- 仅暴露 40005；管理 API 不对外映射
