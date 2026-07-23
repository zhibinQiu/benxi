---
name: create_user
---
创建平台用户（需管理员权限）。

## When to use
- 管理员要求开通新账号

## When NOT to use
- 非管理场景
- 更新已有用户（用 update_user）

## Returns
- 新建用户信息

## Parameters

### phone (required)
手机号。

### email (required)
邮箱。

### display_name (required)
显示名。

### password (required)
初始密码（至少 6 位）。

### status (optional)
默认 active。

### department_id / department_name (optional)
所属部门。
