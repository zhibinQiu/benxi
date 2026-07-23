---
name: list_users
---
分页列出平台用户（需管理员权限）。

## When to use
- 管理场景：查看用户列表、按关键词搜索用户

## When NOT to use
- 非管理员/非用户管理场景
- 创建/更新/删除用户（用对应工具）

## Returns
- 用户分页列表

## Parameters

### page (optional)
页码，默认 1。

### page_size (optional)
每页条数，默认 20，最大 100。

### keyword (optional)
姓名/手机/邮箱等关键词。
