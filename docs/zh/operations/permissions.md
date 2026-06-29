# 权限与账户

## 认证

- **JWT** Bearer（`Authorization: Bearer <token>`）
- 登录：`POST /api/v1/auth/login`（手机号 + 密码）
- 注册：`POST /api/v1/auth/register`（可配置 `allow_public_register`）
- Bootstrap 管理员：`BOOTSTRAP_ADMIN_*` 环境变量，首次启动 seed

## RBAC

| 实体 | 说明 |
|------|------|
| User | 用户；**至多归属一个**部门（见 `user_departments`） |
| Role | 角色：`sys_admin`（系统管理员）、`member`（普通用户）等 |
| Permission | 权限码，如 `admin.user`、`doc.company.create` |
| UserRole / RolePermission | 多对多 |

**系统管理员：** 持有 `sys_admin` 角色的用户跳过权限检查，并对所有文档分级具备完整 ACL bypass。历史上独立的分级管理员角色已废弃。

### 功能权限

每个 `FeaturePlugin` 注册 `permission_code`（如 `feature.data_analysis`），启动时写入 DB 并授予默认角色。

前端路由 `meta.perm` 与侧栏菜单按 `hasPerm()` 过滤。

### 管理权限

| 权限码 | 能力 |
|--------|------|
| `admin.user` | 用户管理、菜单可见性、**资源管理**（模型/服务/API Key） |
| `admin.dept` | 部门管理 |
| `admin.role` | 角色管理 |
| `admin.audit` | 审计日志 |
| `admin.settings` | 系统设置 |

## 文档分级（Scope）

| Scope | 界面 Tab | 组织树深度 | RBAC 前缀 |
|-------|----------|------------|-----------|
| `company` | 公司级 | 0（根） | `doc.company.*` |
| `department` | 部门级 | 1 | `doc.dept.*` |
| `team` | 分部级 | 2 | `doc.team.*` |
| `personal` | 个人级 | 不绑定 | `doc.personal.*` |

另需 **`doc.read`** 才能默认访问组织文库文档。单文档另有 **ACL**（用户级 grant，档位 `visible` / `query` / `modify`）与 **deny** 规则；组织分级成员默认 **可修改**。deny 优先于 grant 与分级默认。

**完整说明（组织树映射、用户部门、分享 Tab、KnowFlow 对应）：** [权限模型与文档分级](../platform/permission-model.md)

## KnowFlow 账号映射

- 模式 `ragflow_account_mode=mapped`：每平台用户独立 RAGFlow 账号与 personal dataset
- 命名：`zt-platform-{user_id}`、`zt-personal-*`、组织 scope_key 对应共享 dataset 等
- SSO：`rag/embed-session` 自动 provision + 返回 `auth` query
- 系统管理员可配置 `ragflow_grant_global_admin`

## 审计

- 敏感操作写 `audit_logs`
- 监控页需 `admin.audit`

## 生产建议

- 修改默认 `JWT_SECRET`、MinIO 密码、MySQL/ES 密码
- 关闭公开注册或限制网络
- 仅暴露 40005；管理 API 不对外映射
