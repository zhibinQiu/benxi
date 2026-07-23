---
name: update_user
---
更新平台用户资料（需管理员权限）。用 user_id 或 user_name 定位。

## When to use
- 管理员修改用户手机/邮箱/部门/状态/密码等

## When NOT to use
- 创建新用户（用 create_user）
- 删除用户（用 delete_user）

## Returns
- 更新后的用户信息

## Parameters

### user_id / user_name (optional)
定位用户，至少提供一个。

### phone / email / display_name / password / status (optional)
要更新的字段。

### department_id / department_name (optional)
调整部门。

### clear_department (optional)
为 true 时清除部门归属。
