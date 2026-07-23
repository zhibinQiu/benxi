---
name: delete_user
---
删除平台用户。破坏性操作，须 confirm=true（需管理员权限）。

## When to use
- 管理员明确要求删除某账号并已确认

## When NOT to use
- 仅停用账号（用 update_user 改 status）
- 未确认时

## Returns
- 删除结果

## Parameters

### confirm (required)
必须为 true。

### user_id / user_name (optional)
定位用户，至少提供一个。
